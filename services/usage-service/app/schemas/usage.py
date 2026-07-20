from pydantic import BaseModel


class UsageCheckResponse(BaseModel):
    account_id: str
    period: str
    used: int
    quota: int
    remaining: int
    allowed: bool


class ModelUsage(BaseModel):
    model: str
    tokens_used: int
    cost_cents: int


class UsageSummaryResponse(BaseModel):
    account_id: str
    period: str
    total_tokens: int
    total_cost_cents: int
    by_model: list[ModelUsage]
