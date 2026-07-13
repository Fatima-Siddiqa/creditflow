import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---- Passwords ----

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


# ---- Random tokens (refresh / reset / email-verification) ----
# These are high-entropy random strings, not user-chosen secrets, so a fast
# hash (SHA-256) is appropriate here — unlike passwords, which need bcrypt's
# deliberate slowness to resist brute-forcing a low-entropy human choice.

def generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


# ---- JWT ----

def _load_private_key() -> str:
    with open(settings.jwt_private_key_path, "r") as f:
        return f.read()


def _load_public_key() -> str:
    with open(settings.jwt_public_key_path, "r") as f:
        return f.read()


def create_access_token(user_id: uuid.UUID, account_id: uuid.UUID | None, role: str | None) -> tuple[str, str]:
    """Returns (token, jti). Caller is responsible for storing jti in Redis."""
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "account_id": str(account_id) if account_id else None,
        "role": role,
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    token = jwt.encode(payload, _load_private_key(), algorithm=settings.jwt_algorithm)
    return token, jti


def decode_access_token(token: str) -> dict:
    """Raises jwt.InvalidTokenError (or a subclass) on any failure — expired,
    bad signature, malformed, etc. Callers catch and turn into a 401."""
    return jwt.decode(token, _load_public_key(), algorithms=[settings.jwt_algorithm])