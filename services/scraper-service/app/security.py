import jwt

from app.config import settings


def _load_public_key() -> str:
    with open(settings.jwt_public_key_path, "r") as f:
        return f.read()


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, _load_public_key(), algorithms=[settings.jwt_algorithm])