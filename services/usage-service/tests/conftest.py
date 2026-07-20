import os, sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
import redis
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import event

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app
from app.db import get_db, engine, SessionLocal
from app.usage_redis import get_usage_redis

TEST_REDIS_URL = "redis://localhost:6380/15"


@pytest.fixture(scope="session", autouse=True)
def _apply_database_migrations():
    from sqlalchemy import inspect, text

    with engine.begin() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names(schema="usage"))

        required_tables = {"usage_ledger", "processed_events", "usage_threshold_notifications"}
        if not required_tables.issubset(existing_tables):
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS usage"))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS usage.usage_ledger (
                    id BIGSERIAL PRIMARY KEY,
                    account_id VARCHAR NOT NULL,
                    model VARCHAR NOT NULL,
                    tokens_used INTEGER NOT NULL,
                    cost_cents INTEGER NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS usage.processed_events (
                    event_id VARCHAR PRIMARY KEY,
                    processed_at TIMESTAMPTZ DEFAULT now()
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS usage.usage_threshold_notifications (
                    id BIGSERIAL PRIMARY KEY,
                    account_id VARCHAR NOT NULL,
                    period VARCHAR NOT NULL,
                    threshold INTEGER NOT NULL,
                    notified_at TIMESTAMPTZ DEFAULT now(),
                    UNIQUE(account_id, period, threshold)
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_usage_usage_ledger_account_id ON usage.usage_ledger (account_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_usage_processed_events_event_id ON usage.processed_events (event_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_usage_usage_threshold_notifications_account_id ON usage.usage_threshold_notifications (account_id)"))

    yield


@pytest.fixture()
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart(sess, trans):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    yield session
    session.close()
    transaction.rollback()
    connection.close()


@asynccontextmanager
async def _noop_lifespan(app):
    yield


@pytest.fixture()
def test_jti_redis_client():
    """Shared test DB index 15, per docs/CONVENTIONS.md -- stands in for
    auth-service's jti store (index 1) that app.dependencies reads."""
    client = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture()
def test_usage_redis_client(test_jti_redis_client):
    """Same physical test DB (index 15, shared/flushed) as the jti store
    fixture above -- CONVENTIONS.md's shared-test-index note applies to
    every service's Redis usage, not just the jti store, since only one
    service's tests run at a time in this solo workflow. Kept as a
    separate fixture name so tests read clearly about which role they're
    exercising (auth vs. this service's own counters)."""
    return test_jti_redis_client


@pytest.fixture(autouse=True)
def _patch_jti_redis(monkeypatch, test_jti_redis_client):
    monkeypatch.setattr("app.dependencies.redis_client", test_jti_redis_client)


@pytest.fixture(scope="session")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=serialization.NoEncryption()).decode()
    public_pem = private_key.public_key().public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private_pem, public_pem


@pytest.fixture(autouse=True)
def _patch_jwt_public_key(monkeypatch, rsa_keypair):
    _, public_pem = rsa_keypair
    monkeypatch.setattr("app.security._load_public_key", lambda: public_pem)


@pytest.fixture()
def make_token(rsa_keypair):
    private_pem, _ = rsa_keypair

    def _make(jti="test-jti", sub=None, account_id=None, role=None):
        now = datetime.now(timezone.utc)
        payload = {"sub": sub, "account_id": account_id, "role": role, "jti": jti, "iat": now, "exp": now + timedelta(minutes=15)}
        return pyjwt.encode(payload, private_pem, algorithm="RS256")

    return _make


@pytest.fixture()
def client(db_session, test_usage_redis_client):
    def _override_db():
        yield db_session

    def _override_usage_redis():
        return test_usage_redis_client

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_usage_redis] = _override_usage_redis
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(make_token, test_jti_redis_client):
    """Registers a live jti in the (patched) redis client and returns a
    ready-to-use Authorization header for a given account_id/role."""

    def _make(account_id="test_acc_123", role="owner", jti="test-jti"):
        token = make_token(jti=jti, sub="test_user", account_id=account_id, role=role)
        test_jti_redis_client.set(f"jti:{jti}", "1")
        return {"Authorization": f"Bearer {token}"}

    return _make
