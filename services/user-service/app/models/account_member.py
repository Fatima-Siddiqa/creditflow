import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class AccountMember(Base):
    """Composite PK (account_id, user_id) — one row per membership.
    user_id is a plain indexed UUID, deliberately NOT a foreign key into
    auth.users — per CONVENTIONS.md, services never reach into another
    service's schema. Identity ownership stays entirely in auth-service."""
    __tablename__ = "account_members"

    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    role = Column(Enum("owner", "admin", "member", name="account_member_role", schema="tenant"), nullable=False)
    joined_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))