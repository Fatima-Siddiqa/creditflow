import enum
from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.sql import func
from app.db import Base

class ContentStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    PUBLISHED = "published"

class Content(Base):
    __tablename__ = "content"
    id = Column(String, primary_key=True, index=True)
    account_id = Column(String, index=True, nullable=False)
    created_by_user_id = Column(String, nullable=False)
    status = Column(
        Enum(ContentStatus, name="content_status", schema="content", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False, default=ContentStatus.DRAFT,
    )
    image_url = Column(String, nullable=True)
    current_version_id = Column(String, nullable=True)  # informal pointer, no FK (avoids circular constraint with content_versions)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ContentVersion(Base):
    __tablename__ = "content_versions"
    id = Column(String, primary_key=True, index=True)
    content_id = Column(String, ForeignKey("content.id"), nullable=False, index=True)
    body = Column(Text, nullable=False)
    image_url = Column(String, nullable=True)
    created_by_user_id = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ProcessedEvent(Base):
    __tablename__ = "processed_events"
    event_id = Column(String, primary_key=True, index=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())