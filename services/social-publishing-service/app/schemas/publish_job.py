from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PublishJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scheduled_post_id: str
    content_id: str
    status: str
    attempt_count: int
    last_error: Optional[str]
    linkedin_post_urn: Optional[str]
    created_at: datetime