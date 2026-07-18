import jwt
import hashlib
import secrets
from app.config import settings


def _load_public_key() -> str:
    with open(settings.jwt_public_key_path, "r") as f:
        return f.read()


def decode_access_token(token: str) -> dict:
    """Raises jwt.InvalidTokenError (or a subclass, e.g. ExpiredSignatureError)
    on any failure — expired, bad signature, malformed, etc. Callers turn
    that into a 401. This service only ever verifies: it never holds the
    private key and never mints tokens itself (that's auth-service's job,
    via POST /auth/issue-scoped-token for the account-switch case)."""
    return jwt.decode(token, _load_public_key(), algorithms=[settings.jwt_algorithm])


def generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()