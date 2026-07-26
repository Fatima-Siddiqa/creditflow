import os, sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
import redis
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import event, text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app
from app.db import get_db, engine, SessionLocal

TEST_REDIS_URL = "redis://localhost:6380/15"


@pytest.fixture(scope="session", autouse=True)
def _apply_database_migrations():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))

    with engine.begin() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names(schema="admin"))

        try:
            command.upgrade(alembic_cfg, "head")
        except Exception as exc:
            if "already exists" not in str(exc):
                raise
            if "audit_log" not in existing_tables:
                raise

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
    """Skips the real lifespan (which starts the RabbitMQ consumer task) —
    API/RBAC/overview tests don't need a live broker connection. The
    consumer's own logic (_write_audit_row) is exercised directly in
    test_audit_consumer.py instead, same pattern notification-service uses
    for its dispatcher."""
    yield


@pytest.fixture()
def test_redis_client():
    client = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch, test_redis_client):
    """auth_jti_redis_client is imported by name into both app.dependencies
    (get_current_payload) and app.api.admin (sessions endpoints) — patching
    app.redis_client alone wouldn't reach either already-bound reference."""
    monkeypatch.setattr("app.dependencies.auth_jti_redis_client", test_redis_client)
    monkeypatch.setattr("app.api.admin.auth_jti_redis_client", test_redis_client)


@pytest.fixture(autouse=True)
def _clean_admin_tables():
    """audit_log/processed_events rows written via _write_audit_row use
    their own SessionLocal() + commit (mirrors notification-service's
    dispatcher) rather than the rollback-wrapped db_session above, so they
    need an explicit truncate instead of relying on transaction rollback."""
    db = SessionLocal()
    try:
        db.execute(text("TRUNCATE admin.audit_log, admin.processed_events"))
        db.commit()
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        db.execute(text("TRUNCATE admin.audit_log, admin.processed_events"))
        db.commit()
    finally:
        db.close()


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

    def _make(jti="test-jti", sub=None, account_id=None, role=None, platform_role=None):
        now = datetime.now(timezone.utc)
        payload = {
            "sub": sub, "account_id": account_id, "role": role,
            "platform_role": platform_role, "jti": jti,
            "iat": now, "exp": now + timedelta(minutes=15),
        }
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
    """Registers a live jti in the (patched) redis client and returns a
    ready-to-use Authorization header. Pass platform_role='superadmin' for
    SuperAdmin-scoped tests, or account_id/role for TenantAdmin ones."""

    def _make(account_id=None, role=None, platform_role=None, jti="test-jti"):
        token = make_token(jti=jti, sub="test_user", account_id=account_id, role=role, platform_role=platform_role)
        test_redis_client.set(f"jti:{jti}", "1")
        return {"Authorization": f"Bearer {token}"}

    return _make