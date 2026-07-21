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
    from sqlalchemy import inspect, text

    with engine.begin() as conn:
        inspector = inspect(conn)
        existing = set(inspector.get_table_names(schema="content"))
        required = {"content", "content_versions", "processed_events"}
        if not required.issubset(existing):
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS content"))
            conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE content.content_status AS ENUM ('draft', 'approved', 'published');
                EXCEPTION WHEN duplicate_object THEN null;
                END $$;
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS content.content (
                    id VARCHAR PRIMARY KEY,
                    account_id VARCHAR NOT NULL,
                    created_by_user_id VARCHAR NOT NULL,
                    status content.content_status NOT NULL,
                    image_url VARCHAR,
                    current_version_id VARCHAR,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS content.content_versions (
                    id VARCHAR PRIMARY KEY,
                    content_id VARCHAR NOT NULL REFERENCES content.content(id),
                    body TEXT NOT NULL,
                    image_url VARCHAR,
                    created_by_user_id VARCHAR NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS content.processed_events (
                    event_id VARCHAR PRIMARY KEY,
                    processed_at TIMESTAMPTZ DEFAULT now()
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_content_content_account_id ON content.content (account_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_content_content_versions_content_id ON content.content_versions (content_id)"))
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
    client = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()


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

    def _make(jti="test-jti", sub="test_user", account_id="test_acc_123", role="owner"):
        now = datetime.now(timezone.utc)
        payload = {"sub": sub, "account_id": account_id, "role": role, "jti": jti, "iat": now, "exp": now + timedelta(minutes=15)}
        return pyjwt.encode(payload, private_pem, algorithm="RS256")

    return _make


@pytest.fixture()
def client(db_session):
    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(make_token, test_jti_redis_client):
    def _make(account_id="test_acc_123", role="owner", jti="test-jti"):
        token = make_token(jti=jti, sub="test_user", account_id=account_id, role=role)
        test_jti_redis_client.set(f"jti:{jti}", "1")
        return {"Authorization": f"Bearer {token}"}

    return _make

@pytest.fixture(autouse=True)
def captured_events(monkeypatch):
    """No test in this service should depend on a real RabbitMQ broker
    being reachable -- this was the actual root cause of CI failing on
    feature/content-service-tests after merge to dev (GitHub Actions has
    no RabbitMQ service container, so aio_pika.connect_robust() failed
    outright with a connection error on every endpoint that publishes a
    content.* event). It happened to pass locally only because a real
    broker was reachable on localhost there.

    ai-generation-service's tests/conftest.py already established this
    pattern (also named captured_events) -- mirroring it here so every
    content.* event publish is a no-op recorder instead of a real
    network call. Patches app.api.content's imported reference to
    publish_event (not app.events.publisher's own copy), same binding-
    site convention used throughout this project's other services: you
    patch where a name was imported TO, not where it was originally
    defined. Tests that care what got published ask for this fixture by
    name and read the (event_type, payload, account_id) tuples it
    collects; every other test gets it silently and doesn't need to
    change."""
    events = []

    async def _fake_publish(event_type, payload, account_id=None):
        events.append((event_type, payload, account_id))

    monkeypatch.setattr("app.api.content.publish_event", _fake_publish)
    return events