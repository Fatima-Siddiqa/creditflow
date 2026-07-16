import jwt
from fastapi import HTTPException, status

from app.auth_jti_redis_client import auth_jti_redis_client
from app.security import decode_access_token


def _unauthorized(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": code, "message": message, "details": {}}},
    )


def verify_access_token(auth_header: str | None) -> dict:
    """Returns the decoded JWT payload for a valid, non-revoked access
    token. Raises a 401 (our standard error schema) for every failure
    mode, using a distinct `code` per case — specifically `token_expired`,
    which per spec §8 Service 1 is the signal the frontend watches for to
    trigger a silent refresh, rather than an immediate logout."""
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
        # Valid signature, not expired, but absent from auth-service's
        # active-session store — either an explicit logout, or a replay of
        # a token whose session the Admin Service revoked out from under it.
        raise _unauthorized("session_revoked", "This session has been revoked.")

    return payload