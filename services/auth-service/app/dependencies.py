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


def _too_many_attempts() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "error": {
                "code": "too_many_attempts",
                "message": "Too many failed login attempts. Try again later.",
                "details": {},
            }
        },
    )


def check_login_rate_limit(email: str, ip: str) -> None:
    """Two independent dimensions, per spec §8 Service 2 ("Rate-limit
    login attempts per email/IP"): email-scoped (stops brute-forcing ONE
    known account's password) and IP-scoped (stops sweeping MANY
    different emails from one source — email-only limiting can't catch
    this at all, since no single email ever crosses its own threshold).
    Either limit alone lets the other attack through; both are checked."""
    email_attempts = redis_client.get(f"login_attempts:email:{email}")
    if email_attempts and int(email_attempts) >= settings.login_rate_limit_max_attempts:
        raise _too_many_attempts()

    ip_attempts = redis_client.get(f"login_attempts:ip:{ip}")
    if ip_attempts and int(ip_attempts) >= settings.login_rate_limit_max_attempts_per_ip:
        raise _too_many_attempts()


def register_failed_login_attempt(email: str | None, ip: str) -> None:
    """IP-side is ALWAYS registered, even when email is None (i.e. the
    email doesn't belong to a real user) — otherwise sweeping many
    nonexistent emails from one IP would never trip IP-level limiting at
    all, which defeats the point of having it. Email-side is only
    registered for real users, matching this service's existing choice
    not to track attempts against emails that were never signed up."""
    pipe = redis_client.pipeline()
    if email:
        pipe.incr(f"login_attempts:email:{email}")
        pipe.expire(f"login_attempts:email:{email}", settings.login_rate_limit_window_seconds)
    pipe.incr(f"login_attempts:ip:{ip}")
    pipe.expire(f"login_attempts:ip:{ip}", settings.login_rate_limit_window_seconds)
    pipe.execute()


def clear_login_attempts(email: str) -> None:
    """Only clears the EMAIL-scoped counter on a successful login. The IP
    counter is deliberately left alone: if an IP has been sweeping many
    accounts and happens to get one right, that shouldn't wipe its slate
    clean and let it keep trying others — IP-level limiting only decays
    via its own TTL, never via any single account's success."""
    redis_client.delete(f"login_attempts:email:{email}")

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