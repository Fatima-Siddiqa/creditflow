import os
import sys
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app
from app.db import get_db, engine, SessionLocal


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
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()