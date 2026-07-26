import os
import sys

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db import SessionLocal, engine


@pytest.fixture(scope="session", autouse=True)
def _apply_database_migrations():
    from sqlalchemy import inspect

    with engine.begin() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names(schema="notification"))
        required_tables = {"notification_log", "processed_events"}
        if not required_tables.issubset(existing_tables):
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS notification"))
            conn.execute(text(
                "DO $$ BEGIN "
                "CREATE TYPE notification.notification_status AS ENUM ('sent', 'failed'); "
                "EXCEPTION WHEN duplicate_object THEN null; END $$;"
            ))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS notification.notification_log (
                    id UUID PRIMARY KEY,
                    type VARCHAR NOT NULL,
                    recipient VARCHAR NOT NULL,
                    status notification.notification_status NOT NULL,
                    error VARCHAR,
                    sent_at TIMESTAMPTZ DEFAULT now()
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS notification.processed_events (
                    event_id VARCHAR PRIMARY KEY,
                    processed_at TIMESTAMPTZ DEFAULT now()
                )
            """))
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    """Consumer service opens its own short-lived sessions per call, so
    the nested-savepoint rollback trick other services use doesn't apply
    cleanly here -- truncate instead, before and after each test."""
    db = SessionLocal()
    try:
        db.execute(text("TRUNCATE notification.notification_log, notification.processed_events"))
        db.commit()
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        db.execute(text("TRUNCATE notification.notification_log, notification.processed_events"))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def db_session():
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture()
def notification_logs(db_session):
    def _fetch():
        db_session.expire_all()
        rows = db_session.execute(
            text("SELECT type, recipient, status, error FROM notification.notification_log ORDER BY sent_at")
        ).fetchall()
        return [dict(r._mapping) for r in rows]
    return _fetch