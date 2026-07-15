import os
import sys

import pytest
import redis
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


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c