import enum
import uuid

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, String
from sqlalchemy.sql import func

from app.db import Base


class ScheduleStatus(str, enum.Enum):
    PENDING = "pending"
    FIRED = "fired"
    CANCELLED = "cancelled"


class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(String, index=True, nullable=False)
    content_id = Column(String, nullable=False)
    # Captured from content-service at schedule time (POST /schedule
    # forwards the caller's own JWT there) rather than looked up fresh
    # when the beat task fires -- firing runs unattended in Celery with
    # no user JWT to forward, and this project has no service-to-service
    # auth mechanism yet for an unattended cross-service call. Can go
    # stale if the image is added/removed between scheduling and firing;
    # acceptable given the frontend schedules right after finalizing
    # content anyway. Needed in content.scheduled's payload per Phase
    # 10's handoff note to Phase 11 (Social Publishing branches on it).
    has_image = Column(Boolean, nullable=False, default=False)
    publish_at = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(
        Enum(ScheduleStatus, name="schedule_status", schema="scheduler", values_callable=lambda e: [x.value for x in e]),
        nullable=False, default=ScheduleStatus.PENDING,
    )
    # {"freq": "daily"|"weekly"|"monthly", "interval": int, "until": "YYYY-MM-DD"|null}
    recurrence_rule = Column(JSON, nullable=True)
    # Always the SERIES ROOT id (not the immediate predecessor) -- see
    # app/recurrence.py. Null on the root row itself.
    recurrence_parent_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
