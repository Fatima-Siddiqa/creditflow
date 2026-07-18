import jwt
from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session

from app.models import AccountMember
from app.redis_client import redis_client
from app.security import decode_access_token


def _unauthorized(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": code, "message": message, "details": {}}},
    )


def _forbidden(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": {"code": code, "message": message, "details": {}}},
    )


def verify_access_token(auth_header: str | None) -> dict:
    """Same verification this service's tokens go through at the gateway
    — done again here independently (defense in depth per
    docs/ARCHITECTURE.md: 'verified by every other service and the
    gateway using the shared public key', not just the gateway once).
    Identical 4 failure codes as api-gateway's version, for consistency."""
    if not auth_header or not auth_header.startswith("Bearer "):
        raise _unauthorized("missing_token", "Authorization header with a Bearer token is required.")

    token = auth_header.removeprefix("Bearer ").strip()

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("token_expired", "Access token has expired.")
    except jwt.InvalidTokenError:
        raise _unauthorized("invalid_token", "Access token is invalid.")

    jti = payload.get("jti")
    if not jti or not redis_client.exists(f"jti:{jti}"):
        raise _unauthorized("session_revoked", "This session has been revoked.")

    return payload


def get_current_payload(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI-injectable form of verify_access_token — Depends(get_current_payload)
    in endpoint signatures, so each route doesn't need its own Request/header plumbing."""
    return verify_access_token(authorization)


def get_live_membership(db: Session, account_id, user_id) -> AccountMember:
    """Looks up the CURRENT membership row rather than trusting the JWT's
    account_id/role claims — those are a snapshot from whenever the token
    was issued and can go stale before it naturally expires (e.g. a role
    change, or removal from the account entirely). RBAC decisions in this
    service are made against this live row, never against payload
    contents directly.

    Raises 403 if the caller isn't currently a member of account_id at
    all — this also covers the case where the token's own account_id
    claim doesn't match the account_id being accessed, since a
    non-matching account_id will simply never have a membership row for
    this user either."""
    membership = (
        db.query(AccountMember)
        .filter(AccountMember.account_id == account_id, AccountMember.user_id == user_id)
        .first()
    )
    if membership is None:
        raise _forbidden("not_a_member", "You are not a member of this account.")
    return membership


def require_role(membership: AccountMember, allowed_roles: set[str]) -> None:
    if membership.role not in allowed_roles:
        raise _forbidden(
            "insufficient_role",
            f"This action requires one of: {', '.join(sorted(allowed_roles))}.",
        )