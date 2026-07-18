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
from sqlalchemy import event

# Index 15, reserved for tests — never touches the real jti store (index 1).
TEST_REDIS_URL = "redis://localhost:6380/15"

@pytest.fixture()
def db_session():
    """Wraps each test in a transaction rolled back afterward. Uses a
    SAVEPOINT (begin_nested), not just an outer transaction — endpoint
    code under test calls db.commit() directly (e.g. create_team_account),
    and a plain outer-transaction wrapper does NOT survive that: commit()
    ends the real transaction, making the final rollback() a no-op and
    silently leaking real rows into the dev database. The listener below
    reopens a fresh SAVEPOINT every time one closes, so commit() inside
    the endpoint only ever closes the SAVEPOINT, never the real
    transaction — see SQLAlchemy's "Joining a Session into an External
    Transaction" docs, this is their recommended pattern, not a custom
    workaround."""
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

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
def client(db_session, test_redis_client, published_events):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture()
def published_events(monkeypatch):
    """Both app.api.accounts and app.api.invites imported publish_event
    by name at module load time — patching app.events.publisher alone
    wouldn't reach either of them, same reasoning as auth-service's
    conftest.py."""
    calls = []

    async def _fake_publish(event_type, payload, account_id=None):
        calls.append({"event_type": event_type, "payload": payload, "account_id": account_id})

    monkeypatch.setattr("app.api.accounts.publish_event", _fake_publish)
    monkeypatch.setattr("app.api.invites.publish_event", _fake_publish)
    return calls


@pytest.fixture()
def fake_scoped_token(monkeypatch):
    """Stands in for the real POST /auth/issue-scoped-token call — these
    tests never need auth-service running."""
    async def _fake_issue(user_id, account_id, role):
        return {"access_token": "fake-scoped-token", "token_type": "bearer"}

    monkeypatch.setattr("app.api.invites.issue_scoped_token", _fake_issue)
    monkeypatch.setattr("app.api.accounts.issue_scoped_token", _fake_issue)