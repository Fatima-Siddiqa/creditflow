import uuid
from datetime import datetime

from pydantic import BaseModel


class CheckoutSessionRequest(BaseModel):
    plan_tier: str  # "pro" | "team"


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


class PlanChangeRequest(BaseModel):
    plan_tier: str


class RefundRequest(BaseModel):
    stripe_invoice_id: str
    reason: str | None = None


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    stripe_invoice_id: str
    amount_cents: int
    status: str
    created_at: datetime


class SubscriptionResponse(BaseModel):
    account_id: uuid.UUID
    plan_tier: str
    status: str
    current_period_end: datetime | None