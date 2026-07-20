from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.dependencies import get_current_payload, resolve_target_account_id
from app.models.usage import UsageLedger
from app.period import get_current_period, period_bounds
from app.schemas.usage import ModelUsage, UsageCheckResponse, UsageSummaryResponse
from app.usage_redis import get_usage_redis

router = APIRouter()


def _usage_key(account_id: str, period: str) -> str:
    return f"usage:{account_id}:{period}"


@router.get("/check", response_model=UsageCheckResponse)
def check_quota(payload: dict = Depends(get_current_payload), redis_client=Depends(get_usage_redis)):
    """Fast Redis-only pre-check -- called synchronously by
    ai-generation-service (Phase 8) before allowing a generation call.
    account_id always comes from the caller's own JWT, never a query
    param -- this endpoint answers 'can I generate right now', which is
    only ever meaningful for the caller's own account."""
    account_id = payload["account_id"]
    period = get_current_period()
    used = int(redis_client.get(_usage_key(account_id, period)) or 0)
    quota = settings.default_monthly_token_quota
    remaining = max(quota - used, 0)
    return UsageCheckResponse(
        account_id=account_id, period=period, used=used, quota=quota, remaining=remaining, allowed=used < quota
    )


@router.get("/summary", response_model=UsageSummaryResponse)
def usage_summary(account_id: str = Depends(resolve_target_account_id), db: Session = Depends(get_db)):
    """Ledger-backed (never Redis) -- this is the accurate, by-model
    breakdown for the frontend Owner Dashboard and, eventually, the Admin
    dashboard (spec §8 Service 6 & Service 13)."""
    period = get_current_period()
    start, end = period_bounds(period)

    rows = (
        db.query(UsageLedger.model, func.sum(UsageLedger.tokens_used), func.sum(UsageLedger.cost_cents))
        .filter(UsageLedger.account_id == account_id, UsageLedger.created_at >= start, UsageLedger.created_at < end)
        .group_by(UsageLedger.model)
        .all()
    )
    by_model = [ModelUsage(model=m, tokens_used=int(t or 0), cost_cents=int(c or 0)) for m, t, c in rows]
    return UsageSummaryResponse(
        account_id=account_id,
        period=period,
        total_tokens=sum(x.tokens_used for x in by_model),
        total_cost_cents=sum(x.cost_cents for x in by_model),
        by_model=by_model,
    )
