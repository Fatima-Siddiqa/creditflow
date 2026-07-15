import os
import sys

import pytest
import redis
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app
from app.db import get_db, engine, SessionLocal

# Index 15, reserved for tests — never touched by the dev service (index 1)
# or by you manually poking at things in the RabbitMQ/Redis UI.
TEST_REDIS_URL = "redis://localhost:6380/15"


@pytest.fixture()
def db_session():
    """Wraps each test in a transaction that's rolled back afterward, so
    tests never leave rows behind in the `auth` schema — including the one
    you've been testing in manually via psql."""
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def test_redis_client():
    client = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch, test_redis_client):
    # app/api/auth.py and app/dependencies.py each imported `redis_client` by
    # name at module load time — patching app.redis_client.redis_client alone
    # wouldn't reach either of them, so both need patching individually.
    monkeypatch.setattr("app.api.auth.redis_client", test_redis_client)
    monkeypatch.setattr("app.dependencies.redis_client", test_redis_client)


@pytest.fixture()
def published_events(monkeypatch):
    """Replaces the real RabbitMQ publish with an in-memory list — these
    tests never need RabbitMQ running at all, only Postgres and Redis."""
    calls = []

    async def _fake_publish(event_type, payload, account_id=None):
        calls.append({"event_type": event_type, "payload": payload, "account_id": account_id})

    monkeypatch.setattr("app.api.auth.publish_event", _fake_publish)
    return calls


@pytest.fixture()
def client(db_session, published_events):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()