import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    is_verified = Column(Boolean, nullable=False, default=False)
    platform_role = Column(String, nullable=True)  # None | "superadmin" — platform-level, not account-scoped (spec §8 Service 13)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))