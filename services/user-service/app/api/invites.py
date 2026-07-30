import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_payload, get_live_membership, require_role
from app.events import publish_event
from app.internal_auth_client import issue_scoped_token
from app.models import AccountMember, Invite
from app.schemas import AcceptInviteResponse, CreateInviteRequest, InviteResponse
from app.security import generate_raw_token, hash_token

router = APIRouter()

INVITE_TTL_DAYS = 7
from app.constants import VALID_ROLES

def _bad_request(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error": {"code": code, "message": message, "details": {}}},
    )


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": {"code": code, "message": message, "details": {}}},
    )


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error": {"code": code, "message": message, "details": {}}},
    )


@router.post("/accounts/{account_id}/invites", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
async def create_invite(
    account_id: uuid.UUID,
    body: CreateInviteRequest,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    """Owner/admin only — spec §8 Service 3: 'Team invite flow ...
    restricted to owner/admin.'"""
    if body.role not in VALID_ROLES:
        raise _bad_request("invalid_role", f"role must be one of: {', '.join(sorted(VALID_ROLES))}.")

    user_id = uuid.UUID(payload["sub"])
    membership = get_live_membership(db, account_id, user_id)
    require_role(membership, {"owner", "admin"})

    raw_token = generate_raw_token()
    # notification-service (Phase 13) doesn't exist yet — same dev-console
    # fallback auth-service uses for signup/forgot-password, so invites
    # can be tested end-to-end locally without a real email provider.
    print(f"[DEV] Invite token for {body.email} to account {account_id}: {raw_token}")

    invite = Invite(
        account_id=account_id,
        email=body.email,
        role=body.role,
        token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    await publish_event(
        "invite.created",
        payload={
            "invite_id": str(invite.id),
            "account_id": str(account_id),
            "email": invite.email,
            "role": invite.role,
        },
        account_id=account_id,
    )

    return InviteResponse(
        id=invite.id, account_id=invite.account_id, email=invite.email,
        role=invite.role, expires_at=invite.expires_at, accepted=invite.accepted,
    )


@router.post("/invites/{token}/accept", response_model=AcceptInviteResponse)
async def accept_invite(
    token: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    """Caller must be authenticated (any valid token, account-agnostic is
    fine — same reasoning as create_team_account). Does NOT verify the
    invite's email matches the caller's own email: user-service has no
    access to auth-service's email data without a new lookup endpoint
    there, which is out of this PR's scope. Documented gap: anyone
    holding a valid invite token plus any authenticated session can
    accept it, regardless of which email it was addressed to."""
    user_id = uuid.UUID(payload["sub"])
    token_hash = hash_token(token)

    invite = db.query(Invite).filter(Invite.token_hash == token_hash).first()
    if invite is None:
        raise _not_found("invalid_invite", "Invite token is invalid.")
    if invite.accepted:
        raise _bad_request("invite_already_used", "This invite has already been accepted.")
    if invite.expires_at < datetime.now(timezone.utc):
        raise _bad_request("invite_expired", "This invite has expired.")

    existing = (
        db.query(Invite)
        .filter(Invite.account_id == account_id, Invite.email == body.email, Invite.accepted == False)
        .first()
    )
    raw_token = generate_raw_token()
    if existing is not None:
        existing.role = body.role
        existing.token_hash = hash_token(raw_token)
        existing.expires_at = datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)
        invite = existing
    else:
        invite = Invite(account_id=account_id, email=body.email, role=body.role,
                        token_hash=hash_token(raw_token),
                        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS))
        db.add(invite)
    db.commit()
    db.refresh(invite)

    await publish_event("invite.created", payload={
        "invite_id": str(invite.id), "account_id": str(account_id),
        "email": invite.email, "role": invite.role, "token": raw_token,
    })

    try:
        token_data = await issue_scoped_token(user_id, invite.account_id, invite.role)
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "auth_service_unavailable",
                    "message": "Could not mint account-scoped session.",
                    "details": {},
                }
            },
        )

    return AcceptInviteResponse(
        access_token=token_data["access_token"],
        account_id=invite.account_id,
        role=invite.role,
    )

@router.get("/accounts/{account_id}/invites", response_model=list[InviteResponse])
def list_invites(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    """Owner/admin only — pending invites shown alongside the roster."""
    user_id = uuid.UUID(payload["sub"])
    membership = get_live_membership(db, account_id, user_id)
    require_role(membership, {"owner", "admin"})

    invites = (
        db.query(Invite)
        .filter(Invite.account_id == account_id, Invite.accepted == False)  # noqa: E712
        .order_by(Invite.expires_at.desc())
        .all()
    )
    return [
        InviteResponse(id=i.id, account_id=i.account_id, email=i.email, role=i.role, expires_at=i.expires_at, accepted=i.accepted)
        for i in invites
    ]