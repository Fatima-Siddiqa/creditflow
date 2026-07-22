from cryptography.fernet import Fernet
from app.config import settings


def _fernet() -> Fernet:
    return Fernet(settings.token_encryption_key.encode())


def encrypt(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt(token_enc: str) -> str:
    return _fernet().decrypt(token_enc.encode()).decode()