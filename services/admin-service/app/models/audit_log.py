import uuid
from sqlalchemy import BigInteger, Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db import Base


class AuditLog(Base):
    """The one deliberate 'consume everything' exception — Phase 1's
    topology doc. Every domain event across all 10 exchanges lands here."""

    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    account_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    payload = Column(JSONB, nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now())