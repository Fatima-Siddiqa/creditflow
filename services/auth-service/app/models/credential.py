from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class Credential(Base):
    __tablename__ = "credentials"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    password_hash = Column(String, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )