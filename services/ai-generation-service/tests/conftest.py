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

TEST_REDIS_URL = "redis://localhost:6380/15"


@pytest.fixture(scope="session", autouse=True)
def _apply_database_migrations():
    """Makes `pytest` self-sufficient without requiring `alembic upgrade
    head` to be run first -- mirrors usage-service's tests/conftest.py."""
    from sqlalchemy import inspect, text

    with engine.begin() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names(schema="ai"))

        required_tables = {"generation_jobs", "prompt_history"}
        if not required_tables.issubset(existing_tables):
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS ai"))
            conn.execute(text("DO $$ BEGIN CREATE TYPE ai.generationstatus AS ENUM ('RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'); EXCEPTION WHEN duplicate_object THEN null; END $$;"))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ai.generation_jobs (
                    id VARCHAR PRIMARY KEY,
                    account_id VARCHAR NOT NULL,
                    created_by_user_id VARCHAR NOT NULL,
                    model VARCHAR NOT NULL,
                    status ai.generationstatus NOT NULL,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    total_tokens INTEGER,
                    cost_cents INTEGER,
                    error_reason VARCHAR,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    completed_at TIMESTAMPTZ
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ai.prompt_history (
                    id VARCHAR PRIMARY KEY,
                    job_id VARCHAR NOT NULL REFERENCES ai.generation_jobs(id),
                    account_id VARCHAR NOT NULL,
                    prompt TEXT NOT NULL,
                    response TEXT,
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_generation_jobs_account_id ON ai.generation_jobs (account_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_prompt_history_account_id ON ai.prompt_history (account_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_prompt_history_job_id ON ai.prompt_history (job_id)"))

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
def client(db_session, test_redis_client):
    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(make_token, test_redis_client):
    def _make(account_id="test_acc_123", role="owner", jti="test-jti", sub="test_user"):
        token = make_token(jti=jti, sub=sub, account_id=account_id, role=role)
        test_redis_client.set(f"jti:{jti}", "1")
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture()
def mock_quota_allowed(monkeypatch):
    """Per docs/CONVENTIONS.md, no service's tests depend on another
    service actually running -- usage-service's GET /usage/check is
    monkeypatched here rather than called for real."""

    async def _allowed(authorization):
        return {"account_id": "test_acc_123", "period": "2026-07", "used": 0, "quota": 100_000, "remaining": 100_000, "allowed": True}

    monkeypatch.setattr("app.api.generation.check_quota", _allowed)


@pytest.fixture()
def mock_quota_exhausted(monkeypatch):
    async def _blocked(authorization):
        return {"account_id": "test_acc_123", "period": "2026-07", "used": 100_000, "quota": 100_000, "remaining": 0, "allowed": False}

    monkeypatch.setattr("app.api.generation.check_quota", _blocked)

@pytest.fixture(autouse=True)
def _patch_sse_redis(monkeypatch, test_redis_client):
    """Same index-15 shared test Redis as everything else (see
    docs/CONVENTIONS.md's Redis logical DB table) -- just patched into
    app.sse_publisher's module-level reference instead of
    app.dependencies', since that's the name PUBLISH calls actually go
    through (app/sse_publisher.py)."""
    monkeypatch.setattr("app.sse_publisher.sse_redis_client", test_redis_client)


@pytest.fixture()
def mock_openrouter_stream(monkeypatch):
    """Patches app.generation_worker's imported reference to
    stream_chat_completion (not the openrouter_client module directly --
    same binding-site convention as mock_quota_allowed above) with a
    fast async generator, so tests never make a real network call."""

    def _install(chunks):
        async def _fake_stream(model, prompt):
            for chunk in chunks:
                yield chunk

        monkeypatch.setattr("app.generation_worker.stream_chat_completion", _fake_stream)

    return _install

@pytest.fixture(autouse=True)
def captured_events(monkeypatch):
    """Autouse so no pre-existing test (written before PR #4 added
    RabbitMQ publishing in app/generation_worker.py) needs to change to
    avoid a real network call to RabbitMQ -- app.generation_worker's
    imported reference to publish_event is replaced with a no-op
    recorder by default (same binding-site convention as
    mock_openrouter_stream above: patch where it's imported TO, not
    where it's defined). Tests that care what got published ask for
    this fixture by name and read the (event_type, payload, account_id)
    tuples it collects."""
    events = []

    async def _fake_publish(event_type, payload, account_id=None):
        events.append((event_type, payload, account_id))

    monkeypatch.setattr("app.generation_worker.publish_event", _fake_publish)
    return events

@pytest.fixture()
def mock_openrouter_error(monkeypatch):
    from app.openrouter_client import OpenRouterError

    def _install(reason="OpenRouter timed out"):
        async def _fake_stream(model, prompt):
            raise OpenRouterError(reason)
            yield  # pragma: no cover - makes this an async generator

        monkeypatch.setattr("app.generation_worker.stream_chat_completion", _fake_stream)

    return _install