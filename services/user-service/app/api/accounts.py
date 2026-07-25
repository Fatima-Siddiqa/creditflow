import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies import get_current_payload, get_live_membership, require_role, verify_internal_service_secret
from app.internal_auth_client import issue_scoped_token
from app.models import Account, AccountMember
from app.events import publish_event
from app.constants import VALID_ROLES
from app.schemas import (
    AcceptInviteResponse, AccountResponse, AccountSummary, CreateAccountRequest,
    MemberResponse, UpdateMemberRoleRequest, AccountOwnerResponse,
)
router = APIRouter()


def _to_account_response(db: Session, account: Account) -> AccountResponse:
    seat_count = db.query(func.count(AccountMember.user_id)).filter(
        AccountMember.account_id == account.id
    ).scalar()
    return AccountResponse(
        id=account.id,
        type=account.type,
        name=account.name,
        plan_tier=account.plan_tier,
        seat_count=seat_count,
        created_at=account.created_at,
    )

def _get_member_or_404(db: Session, account_id: uuid.UUID, user_id: uuid.UUID) -> AccountMember:
    """Distinct from get_live_membership in dependencies.py — that one's
    error message ('You are not a member') describes the CALLER. This
    looks up the TARGET user being managed, which needs its own 404 with
    a message that actually matches what's being checked."""
    member = (
        db.query(AccountMember)
        .filter(AccountMember.account_id == account_id, AccountMember.user_id == user_id)
        .first()
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "member_not_found", "message": "This user is not a member of this account.", "details": {}}},
        )
    return member


def _count_owners(db: Session, account_id: uuid.UUID) -> int:
    return (
        db.query(AccountMember)
        .filter(AccountMember.account_id == account_id, AccountMember.role == "owner")
        .count()
    )

@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_team_account(
    body: CreateAccountRequest,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    user_id = uuid.UUID(payload["sub"])

    account = Account(type="team", name=body.name, plan_tier="free")
    db.add(account)
    db.flush()

    db.add(AccountMember(account_id=account.id, user_id=user_id, role="owner"))
    db.commit()
    db.refresh(account)

    await publish_event(
        "account.created",
        payload={"account_id": str(account.id), "type": account.type, "name": account.name},
        account_id=account.id,
    )

    return _to_account_response(db, account)


@router.get("/accounts/mine", response_model=list[AccountSummary])
def list_my_accounts(
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    """Powers the account switcher. Self-only by construction — the caller
    identity comes from their own JWT (payload['sub']), not a path param,
    so there's no other user's memberships this endpoint could even be
    asked to return. Registered ABOVE /accounts/{account_id} deliberately:
    FastAPI matches routes top-to-bottom, and 'mine' would otherwise be
    swallowed by {account_id}'s UUID parser as if it were a malformed ID."""
    user_id = uuid.UUID(payload["sub"])

    rows = (
        db.query(AccountMember, Account)
        .join(Account, Account.id == AccountMember.account_id)
        .filter(AccountMember.user_id == user_id)
        .all()
    )

    return [
        AccountSummary(
            account_id=account.id,
            name=account.name,
            type=account.type,
            plan_tier=account.plan_tier,
            role=membership.role,
        )
        for membership, account in rows
    ]


@router.get("/accounts/{account_id}", response_model=AccountResponse)
def get_account_profile(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    """Profile data for the dashboard header. Any role can view (no
    require_role call) — but you must be a live member of THIS specific
    account to see anything about it at all, per spec §6: 'All domain
    data is scoped by account_id.'"""
    user_id = uuid.UUID(payload["sub"])
    get_live_membership(db, account_id, user_id)  # raises 403 if not a member

    account = db.query(Account).filter(Account.id == account_id).first()
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "account_not_found", "message": "Account does not exist.", "details": {}}},
        )

    return _to_account_response(db, account)

@router.post("/accounts/{account_id}/switch", response_model=AcceptInviteResponse)
async def switch_account(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    user_id = uuid.UUID(payload["sub"])
    membership = get_live_membership(db, account_id, user_id)

    try:
        token_data = await issue_scoped_token(user_id, account_id, membership.role)
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "auth_service_unavailable", "message": "Could not mint account-scoped session.", "details": {}}},
        )

    return AcceptInviteResponse(access_token=token_data["access_token"], account_id=account_id, role=membership.role)

@router.patch("/accounts/{account_id}/members/{user_id}", response_model=MemberResponse)
async def update_member_role(
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    body: UpdateMemberRoleRequest,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    """Owner/admin only — spec §8 Service 3: 'Role update / member
    removal endpoints, restricted to owner/admin.' No restriction beyond
    that on WHICH member's role can be changed — an admin can currently
    change an owner's role too, not just other admins/members. Documented
    simplification, not an oversight: the spec only restricts who may
    call this, not who may be acted on."""
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_role", "message": f"role must be one of: {', '.join(sorted(VALID_ROLES))}.", "details": {}}},
        )

    caller_id = uuid.UUID(payload["sub"])
    caller_membership = get_live_membership(db, account_id, caller_id)
    require_role(caller_membership, {"owner", "admin"})

    target = _get_member_or_404(db, account_id, user_id)

    if target.role == body.role:
        return MemberResponse(account_id=target.account_id, user_id=target.user_id, role=target.role, joined_at=target.joined_at)

    if target.role == "owner" and body.role != "owner" and _count_owners(db, account_id) == 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "last_owner", "message": "Cannot change the role of the last owner.", "details": {}}},
        )

    target.role = body.role
    db.commit()
    db.refresh(target)

    await publish_event(
        "member.role_updated",
        payload={"account_id": str(account_id), "user_id": str(user_id), "role": target.role},
        account_id=account_id,
    )

    return MemberResponse(account_id=target.account_id, user_id=target.user_id, role=target.role, joined_at=target.joined_at)


@router.delete("/accounts/{account_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    """Owner/admin only — same spec bullet as update_member_role. The
    last-owner guard here is also, incidentally, what protects individual
    accounts (exactly one member, who is always the owner) from ever
    being left with zero members — no separate 'last member' check
    needed, since an individual account's sole member is always its
    owner, and this guard already blocks removing that owner."""
    caller_id = uuid.UUID(payload["sub"])
    caller_membership = get_live_membership(db, account_id, caller_id)
    require_role(caller_membership, {"owner", "admin"})

    target = _get_member_or_404(db, account_id, user_id)

    if target.role == "owner" and _count_owners(db, account_id) == 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "last_owner", "message": "Cannot remove the last owner.", "details": {}}},
        )

    db.delete(target)
    db.commit()

    await publish_event(
        "member.removed",
        payload={"account_id": str(account_id), "user_id": str(user_id)},
        account_id=account_id,
    )

@router.get(
    "/accounts/internal/{account_id}/owner",
    response_model=AccountOwnerResponse,
    dependencies=[Depends(verify_internal_service_secret)],
)
def get_account_owner(account_id: uuid.UUID, db: Session = Depends(get_db)):
    """Internal, service-to-service only. Added in Phase 13 for
    notification-service. Returns the first owner found -- individual
    accounts have exactly one member (always owner); team accounts may
    have several owners, any one of whom is a reasonable notification
    recipient for account-level events."""
    member = (
        db.query(AccountMember)
        .filter(AccountMember.account_id == account_id, AccountMember.role == "owner")
        .first()
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "owner_not_found", "message": "No owner found for this account.", "details": {}}},
        )
    return AccountOwnerResponse(account_id=account_id, user_id=member.user_id, role=member.role)