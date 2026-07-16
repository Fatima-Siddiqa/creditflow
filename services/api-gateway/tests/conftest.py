import os
import sys
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
import redis
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app

# Index 15, reserved for tests — never touched by the dev gateway (index 0).
TEST_REDIS_URL = "redis://localhost:6380/15"


@pytest.fixture()
def test_redis_client():
    client = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch, test_redis_client):
    monkeypatch.setattr("app.main.redis_client", test_redis_client)
    # Same test-Redis db stands in for auth-service's jti store too — the
    # gateway only ever calls .exists() on it, and these tests just need
    # something real to check jti presence/absence against.
    monkeypatch.setattr("app.dependencies.auth_jti_redis_client", test_redis_client)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def rsa_keypair():
    """A throwaway RS256 keypair, generated fresh per test session — kept
    entirely separate from the real keys/jwt_private.pem (gitignored, and
    shouldn't exist in CI at all). Lets these tests mint tokens with a
    known-good signature without touching real key files."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


@pytest.fixture(autouse=True)
def _patch_jwt_public_key(monkeypatch, rsa_keypair):
    _, public_pem = rsa_keypair
    monkeypatch.setattr("app.security._load_public_key", lambda: public_pem)


@pytest.fixture()
def make_token(rsa_keypair):
    private_pem, _ = rsa_keypair

    def _make(jti="test-jti", sub="user-1", account_id="account-1", role="owner", expired=False):
        now = datetime.now(timezone.utc)
        payload = {
            "sub": sub,
            "account_id": account_id,
            "role": role,
            "jti": jti,
            "iat": now,
            "exp": now - timedelta(minutes=1) if expired else now + timedelta(minutes=15),
        }
        return pyjwt.encode(payload, private_pem, algorithm="RS256")

    return _make