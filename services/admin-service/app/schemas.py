from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


class SessionInfo(BaseModel):
    jti: str
    ttl_seconds: int


class AuditLogEntry(BaseModel):
    event_id: str
    event_type: str
    account_id: Optional[str] = None
    payload: dict
    occurred_at: datetime


class AccountOverview(BaseModel):
    account_id: str
    plan_tier: str
    seat_count: int
    credit_balance: int
    usage_tokens_this_period: int
    usage_cost_cents_this_period: int