import jwt

from app.config import settings


def _load_public_key() -> str:
    with open(settings.jwt_public_key_path, "r") as f:
        return f.read()


def decode_access_token(token: str) -> dict:
    """Raises jwt.InvalidTokenError (or a subclass, e.g. ExpiredSignatureError)
    on any failure — expired, bad signature, malformed, etc. Callers turn
    that into a 401. The gateway only ever verifies: it never holds the
    private key and never mints tokens itself."""
    return jwt.decode(token, _load_public_key(), algorithms=[settings.jwt_algorithm])