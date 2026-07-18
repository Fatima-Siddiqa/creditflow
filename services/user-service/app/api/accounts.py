import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_payload, get_live_membership
from app.models import Account, AccountMember
from app.schemas import AccountResponse, AccountSummary, CreateAccountRequest

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


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_team_account(
    body: CreateAccountRequest,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    """Any authenticated user can create a team account, regardless of
    which (if any) account their current token is scoped to — per spec
    §8 Service 3: 'support explicit create team flow (type: team)'.
    Deliberately does NOT require an already-account-scoped token: a
    plain login token (account_id=null) is enough, since you don't need
    to already belong to an account to create a new one."""
    user_id = uuid.UUID(payload["sub"])

    account = Account(type="team", name=body.name, plan_tier="free")
    db.add(account)
    db.flush()  # assigns account.id before the membership row references it

    db.add(AccountMember(account_id=account.id, user_id=user_id, role="owner"))
    db.commit()
    db.refresh(account)

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