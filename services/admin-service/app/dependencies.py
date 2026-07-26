import jwt
from fastapi import Depends, Header, HTTPException, status

from app.security import decode_access_token
from app.redis_client import auth_jti_redis_client


def _unauthorized(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=401, detail={"error": {"code": code, "message": message, "details": {}}})


def _forbidden(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"error": {"code": code, "message": message, "details": {}}})


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
    if not jti or not auth_jti_redis_client.exists(f"jti:{jti}"):
        raise _unauthorized("session_revoked", "This session has been revoked.")
    return payload


def get_current_payload(authorization: str | None = Header(default=None)) -> dict:
    return verify_access_token(authorization)


def require_admin_access(target_account_id: str | None, payload: dict) -> None:
    """SuperAdmin (platform_role == 'superadmin') may access anything,
    including target_account_id=None (cross-account views). TenantAdmin
    (role owner/admin within their own account) may only access their
    own account_id. Anyone else gets 403. Kept as a plain function (not
    a FastAPI dependency) since which account_id is being targeted is
    often only known after parsing query params in the route itself."""
    if payload.get("platform_role") == "superadmin":
        return
    if target_account_id is not None and payload.get("account_id") == target_account_id and payload.get("role") in ("owner", "admin"):
        return
    raise _forbidden("insufficient_role", "SuperAdmin or account owner/admin access required.")