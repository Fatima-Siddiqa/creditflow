import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class CreateInviteRequest(BaseModel):
    email: EmailStr
    role: str  # validated against the real role set in the endpoint, not
               # here — keeps the schema/business-rule boundary consistent
               # with how role handling works elsewhere in this service.


class InviteResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    accepted: bool


class AcceptInviteResponse(BaseModel):
    """No refresh_token here — same reasoning as auth-service's own
    ScopedTokenResponse: this re-scopes the access token only, the user's
    existing (account-agnostic) refresh token from login keeps working."""
    access_token: str
    token_type: str = "bearer"
    account_id: uuid.UUID
    role: str