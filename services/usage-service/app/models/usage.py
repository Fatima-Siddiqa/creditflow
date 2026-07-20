from sqlalchemy import BigInteger, Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db import Base


class UsageLedger(Base):
    """Append-only. This table is the durable source of truth for tokens
    and cost -- the Redis counter in app/usage_redis.py is a fast,
    occasionally-drifting cache OVER this table, never the other way
    around. Reconciliation (app/reconciliation.py) always recomputes
    Redis from here, never adjusts this table to match Redis."""

    __tablename__ = "usage_ledger"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(String, index=True, nullable=False)
    model = Column(String, nullable=False)
    tokens_used = Column(Integer, nullable=False)
    cost_cents = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    event_id = Column(String, primary_key=True, index=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())


class UsageThresholdNotification(Base):
    """One row per (account_id, period, threshold) ever crossed --
    existence of the row IS the 'already notified' flag, checked via
    INSERT ... ON CONFLICT DO NOTHING in
    app/events/ai_consumer.py's _check_and_mark_thresholds."""

    __tablename__ = "usage_threshold_notifications"
    __table_args__ = (
        UniqueConstraint("account_id", "period", "threshold", name="uq_usage_threshold_account_period_threshold"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(String, index=True, nullable=False)
    period = Column(String, nullable=False)
    threshold = Column(Integer, nullable=False)
    notified_at = Column(DateTime(timezone=True), server_default=func.now())
