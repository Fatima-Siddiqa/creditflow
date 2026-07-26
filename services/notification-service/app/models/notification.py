import uuid

from sqlalchemy import Column, DateTime, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db import Base


class NotificationLog(Base):
    """One row per send ATTEMPT, success or failure -- this table is the
    auditability proof required by spec §10 Definition of Done / the
    Admin Service's future audit needs. Written even when the email
    provider call itself fails, per PHASE_13's requirement."""

    __tablename__ = "notification_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String, nullable=False)
    recipient = Column(String, nullable=False)
    status = Column(Enum("sent", "failed", name="notification_status", schema="notification"), nullable=False)
    error = Column(String, nullable=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())


class ProcessedEvent(Base):
    """Standard idempotency table (Phase 1 pattern) -- this service
    consumes from more exchanges than any other except Admin, so
    duplicate delivery is a real risk, not a theoretical one."""

    __tablename__ = "processed_events"

    event_id = Column(String, primary_key=True, index=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())