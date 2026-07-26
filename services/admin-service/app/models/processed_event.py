import uuid

from sqlalchemy import Column, DateTime, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db import Base

class ProcessedEvent(Base):
    """Standard idempotency table (Phase 1 pattern) -- this service
    consumes from more exchanges than any other except Admin, so
    duplicate delivery is a real risk, not a theoretical one."""

    __tablename__ = "processed_events"

    event_id = Column(String, primary_key=True, index=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())