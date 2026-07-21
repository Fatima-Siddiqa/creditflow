from datetime import datetime
from pydantic import BaseModel


class ContentCreate(BaseModel):
    body: str
    image_url: str | None = None


class ContentUpdate(BaseModel):
    body: str
    image_url: str | None = None


class ContentResponse(BaseModel):
    id: str
    account_id: str
    created_by_user_id: str
    status: str
    image_url: str | None
    current_version_id: str | None
    body: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True