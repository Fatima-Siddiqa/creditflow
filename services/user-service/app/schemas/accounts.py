import uuid
from datetime import datetime

from pydantic import BaseModel


class CreateAccountRequest(BaseModel):
    name: str


class AccountResponse(BaseModel):
    """Profile data for the dashboard header — spec §8 Service 3:
    'name, plan tier, seat count'. seat_count is computed (COUNT of
    account_members rows), not a stored column — see app/api/accounts.py."""
    id: uuid.UUID
    type: str
    name: str | None
    plan_tier: str
    seat_count: int
    created_at: datetime


class AccountSummary(BaseModel):
    """One entry in the account switcher's list — deliberately includes
    role, unlike AccountResponse, since the switcher needs to show which
    role the CALLER holds in each account, not just the account's own
    data."""
    account_id: uuid.UUID
    name: str | None
    type: str
    plan_tier: str
    role: str