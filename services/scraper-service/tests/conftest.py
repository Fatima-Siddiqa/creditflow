import os
import sys
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import mongomock
import pytest
import redis
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.db as db_module
from app.main import app

@pytest.fixture(autouse=True)
def _mongo_mock(monkeypatch):
    client = mongomock.MongoClient()
    mock_db = client["scraper_test"]
    monkeypatch.setattr(db_module, "scraped_documents", mock_db["scraped_documents"])
    monkeypatch.setattr(db_module, "scrape_jobs", mock_db["scrape_jobs"])
    monkeypatch.setattr(db_module, "recurring_jobs", mock_db["recurring_jobs"])
    import app.job_runner as job_runner
    import app.api.jobs as jobs_api
    import app.events.request_consumer as request_consumer
    import app.recurring_loop as recurring_loop
    monkeypatch.setattr(job_runner, "scraped_documents", mock_db["scraped_documents"])
    monkeypatch.setattr(job_runner, "scrape_jobs", mock_db["scrape_jobs"])
    monkeypatch.setattr(jobs_api, "scrape_jobs", mock_db["scrape_jobs"])
    monkeypatch.setattr(jobs_api, "recurring_jobs", mock_db["recurring_jobs"])
    monkeypatch.setattr(request_consumer, "scrape_jobs", mock_db["scrape_jobs"])
    monkeypatch.setattr(recurring_loop, "recurring_jobs", mock_db["recurring_jobs"])
    yield mock_db


@pytest.fixture(scope="session")
def _rsa_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


@pytest.fixture(autouse=True)
def _patch_jwt_key(monkeypatch, _rsa_keys, tmp_path):
    private_pem, public_pem = _rsa_keys
    pub_path = tmp_path / "jwt_public.pem"
    pub_path.write_bytes(public_pem)
    from app.config import settings
    monkeypatch.setattr(settings, "jwt_public_key_path", str(pub_path))
    return private_pem


@pytest.fixture()
def redis_conn():
    """Same Redis DB the app's redis_client connects to (settings.redis_url),
    so jti writes here are actually visible to auth checks in the app."""
    from app.config import settings
    conn = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    conn.flushdb()
    yield conn
    conn.flushdb()


def _make_token(private_pem: bytes, account_id: str = "acct-1", jti: str = "jti-1") -> str:
    payload = {
        "user_id": "user-1", "account_id": account_id, "role": "owner", "jti": jti,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return pyjwt.encode(payload, private_pem, algorithm="RS256")


@pytest.fixture()
def auth_headers(_patch_jwt_key, redis_conn):
    token = _make_token(_patch_jwt_key)
    redis_conn.set("jti:jti-1", "1", ex=3600)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client(_mongo_mock):
    with TestClient(app) as c:
        yield c