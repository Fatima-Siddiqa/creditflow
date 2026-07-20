import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, String
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class Account(Base):
    """Individual and team workspaces are both rows here — spec §8 Service 3:
    'Individual signups and team workspaces are both modeled as an Account.'"""
    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(Enum("individual", "team", name="account_type", schema="tenant"), nullable=False)
    name = Column(String, nullable=True)
    plan_tier = Column(String, nullable=False, default="free")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))