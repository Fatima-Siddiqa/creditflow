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
def mock_stripe(monkeypatch):
    """Patches the thin stripe_client wrapper functions directly — same
    isolation principle as api-gateway's _forward: one seam to mock, not
    stripe SDK internals."""
    calls = {}

    def _create_customer(account_id):
        calls["create_customer"] = account_id
        return "cus_fake123"

    def _create_checkout_session(stripe_customer_id, plan_tier, success_url, cancel_url):
        calls["create_checkout_session"] = (stripe_customer_id, plan_tier)
        return "https://checkout.stripe.com/fake-session"

    def _update_subscription_plan(stripe_subscription_id, new_plan_tier):
        calls["update_subscription_plan"] = (stripe_subscription_id, new_plan_tier)
        return {}

    def _create_refund(stripe_invoice_id, reason):
        calls["create_refund"] = (stripe_invoice_id, reason)
        return {"id": "re_fake123"}

    monkeypatch.setattr("app.api.billing.create_customer", _create_customer)
    monkeypatch.setattr("app.api.billing.create_checkout_session", _create_checkout_session)
    monkeypatch.setattr("app.api.billing.update_subscription_plan", _update_subscription_plan)
    monkeypatch.setattr("app.api.billing.create_refund", _create_refund)
    return calls