import hmac
import uuid

import jwt
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.redis_client import redis_client
from app.security import decode_access_token

bearer_scheme = HTTPBearer()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "invalid_token", "message": detail, "details": {}}},
    )


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("access token expired")
    except jwt.InvalidTokenError:
        raise _unauthorized("invalid access token")

    jti = payload.get("jti")
    if not jti or not redis_client.exists(f"jti:{jti}"):
        # jti absent from Redis means it was never issued this way, or it
        # was revoked via logout — either way, the token is dead even
        # though its signature and expiry are still technically valid.
        raise _unauthorized("session has been revoked")

    return payload


def check_login_rate_limit(email: str) -> None:
    key = f"login_attempts:{email}"
    attempts = redis_client.get(key)
    if attempts and int(attempts) >= settings.login_rate_limit_max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": {
                    "code": "too_many_attempts",
                    "message": "Too many failed login attempts. Try again later.",
                    "details": {},
                }
            },
        )


def register_failed_login(email: str) -> None:
    key = f"login_attempts:{email}"
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, settings.login_rate_limit_window_seconds)
    pipe.execute()


def clear_login_attempts(email: str) -> None:
    redis_client.delete(f"login_attempts:{email}")

def verify_internal_service_secret(
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
) -> None:
    """Gates POST /auth/issue-scoped-token — the one endpoint in this
    service that mints a JWT without a password check. Only a service that
    knows this shared secret (User/Tenant Service, once Phase 4 exists)
    should ever call it. hmac.compare_digest avoids a timing side-channel
    on the comparison, same reasoning as password/token hash comparisons
    elsewhere in this service."""
    if not x_internal_secret or not hmac.compare_digest(x_internal_secret, settings.internal_service_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "invalid_internal_secret",
                    "message": "Missing or incorrect internal service secret.",
                    "details": {},
                }
            },
        )