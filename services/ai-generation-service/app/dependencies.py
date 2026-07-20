import jwt
from fastapi import Header, HTTPException, status

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