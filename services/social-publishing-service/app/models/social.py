import enum
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.sql import func
from app.db import Base
from datetime import datetime, timezone

class PublishStatus(str, enum.Enum):
    PENDING = "pending"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"

class SocialConnection(Base):
    __tablename__ = "social_connections"
    account_id = Column(String, primary_key=True)
    linkedin_member_urn = Column(String, nullable=False)
    access_token_enc = Column(String, nullable=False)
    refresh_token_enc = Column(String, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)

class PublishJob(Base):
    __tablename__ = "publish_jobs"
    id = Column(String, primary_key=True, index=True)
    scheduled_post_id = Column(String, nullable=False, index=True)
    content_id = Column(String, nullable=False)
    account_id = Column(String, nullable=False, index=True)
    status = Column(Enum(PublishStatus, name="publish_status", schema="social", values_callable=lambda o: [e.value for e in o]), nullable=False, default=PublishStatus.PENDING)
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error = Column(String, nullable=True)
    linkedin_post_urn = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class PostMedia(Base):
    __tablename__ = "post_media"
    id = Column(String, primary_key=True, index=True)
    publish_job_id = Column(String, ForeignKey("publish_jobs.id"), nullable=False)
    linkedin_asset_urn = Column(String, nullable=False)
    image_url = Column(String, nullable=False)

class ProcessedEvent(Base):
    __tablename__ = "processed_events"
    event_id = Column(String, primary_key=True, index=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())