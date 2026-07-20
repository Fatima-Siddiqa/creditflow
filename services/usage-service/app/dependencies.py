import hmac

import jwt
from fastapi import Depends, Header, HTTPException, Query, status

from app.config import settings
from app.redis_client import redis_client
from app.security import decode_access_token


def _unauthorized(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error": {"code": code, "message": message, "details": {}}})


def verify_access_token(auth_header: str | None) -> dict:
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
    return verify_access_token(authorization)


def resolve_target_account_id(
    account_id: str | None = Query(default=None),
    payload: dict = Depends(get_current_payload),
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
) -> str:
    """GET /usage/summary defaults to the caller's own account (self-service
    usage widget -- spec §4 Owner Dashboard: 'account-wide summary: usage,
    credits, team size, plan tier'). Reading a DIFFERENT account's summary
    is for admin-service's future read-only pull (spec §8 Service 13:
    'Usage & credits overview ... pulled from ... Usage ... services
    (read-only calls, no writes)') and requires the shared internal-service
    secret, not just any valid JWT -- mirrors auth-service's
    verify_internal_service_secret gate on POST /issue-scoped-token."""
    own_account_id = payload["account_id"]
    if account_id is None or account_id == own_account_id:
        return own_account_id
    if x_internal_secret and hmac.compare_digest(x_internal_secret, settings.internal_service_secret):
        return account_id
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": {"code": "forbidden", "message": "Cannot view another account's usage summary.", "details": {}}},
    )
