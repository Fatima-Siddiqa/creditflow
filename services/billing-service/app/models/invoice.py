import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    stripe_invoice_id = Column(String, nullable=False, unique=True)
    amount_cents = Column(Integer, nullable=False)
    status = Column(String, nullable=False)  # paid|payment_failed
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))