from sqlalchemy import Column, DateTime, func
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class ProcessedEvent(Base):
    """Idempotency ledger for this service's RabbitMQ consumers (PR #2
    onward) — one row per event_id ever successfully processed. Per
    docs/EVENT_CONTRACTS.md's idempotency pattern: the insert happens in
    the SAME transaction as the business-logic write it guards."""
    __tablename__ = "processed_events"

    event_id = Column(UUID(as_uuid=True), primary_key=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())