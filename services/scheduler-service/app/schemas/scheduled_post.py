from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class RecurrenceRule(BaseModel):
    freq: str  # daily|weekly|monthly
    interval: int = 1
    until: Optional[str] = None  # YYYY-MM-DD


class ScheduleCreate(BaseModel):
    content_id: str
    publish_at: datetime
    recurrence_rule: Optional[RecurrenceRule] = None


class RescheduleRequest(BaseModel):
    publish_at: datetime


class ScheduledPostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    content_id: str
    has_image: bool
    publish_at: datetime
    status: str
    recurrence_rule: Optional[dict]
    recurrence_parent_id: Optional[str]
    created_at: datetime