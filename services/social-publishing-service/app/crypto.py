from cryptography.fernet import Fernet
from app.config import settings

_f = Fernet(settings.token_encryption_key.encode())

def encrypt(token: str) -> str:
    return _f.encrypt(token.encode()).decode()

def decrypt(token_enc: str) -> str:
    return _f.decrypt(token_enc.encode()).decode()