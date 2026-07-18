import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
import redis
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app
from app.db import get_db, engine, SessionLocal

# Index 15, reserved for tests — never touches the real jti store (index 1).
TEST_REDIS_URL = "redis://localhost:6380/15"


@pytest.fixture()
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@asynccontextmanager
async def _noop_lifespan(app):
    """Replaces app.main's real lifespan for HTTP endpoint tests only.
    The real lifespan starts the identity-events consumer, which tries to
    open a live RabbitMQ connection on startup — irrelevant to these
    tests and, when no broker is reachable locally, capable of hanging
    the whole suite on teardown (connect_robust's retry loop doesn't
    always cancel promptly). The consumer's actual logic is covered
    directly by test_identity_consumer.py without touching the app or
    any broker at all — this fixture doesn't lose coverage, it just stops
    duplicating a connection attempt that nothing here needed."""
    yield


@pytest.fixture()
def test_redis_client():
    client = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch, test_redis_client):
    monkeypatch.setattr("app.dependencies.redis_client", test_redis_client)


@pytest.fixture(scope="session")
def rsa_keypair():
    """A throwaway RS256 keypair, generated fresh per test session —
    entirely separate from the real keys/jwt_private.pem (gitignored, and
    shouldn't exist in CI at all)."""
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

    def _make(jti="test-jti", sub=None, account_id=None, role=None, expired=False):
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


@pytest.fixture()
def client(db_session, test_redis_client):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()