from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.clients import get_account_profile, get_credit_balance, get_usage_summary, list_accounts
from app.db import get_db
from app.dependencies import get_current_payload, require_admin_access
from app.models import AuditLog
from app.redis_client import auth_jti_redis_client
from app.schemas import AccountOverview, AuditLogEntry, SessionInfo

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/sessions", response_model=list[SessionInfo])
def list_sessions(account_id: str = Query(...), payload: dict = Depends(get_current_payload)):
    require_admin_access(account_id, payload)
    # Per-account jti tracking isn't in Redis today (auth-service stores
    # jti:{jti} -> "1" with no account_id tag) — a full KEYS scan is the
    # documented, project-size-acceptable fallback per PHASE_14's own text.
    keys = auth_jti_redis_client.keys("jti:*")
    return [SessionInfo(jti=k.removeprefix("jti:"), ttl_seconds=auth_jti_redis_client.ttl(k)) for k in keys]


@router.delete("/sessions/{jti}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(jti: str, payload: dict = Depends(get_current_payload)):
    if payload.get("platform_role") != "superadmin":
        raise HTTPException(status_code=403, detail={"error": {"code": "insufficient_role", "message": "SuperAdmin only.", "details": {}}})
    auth_jti_redis_client.delete(f"jti:{jti}")


@router.get("/accounts")
async def cross_account_directory(search: str | None = None, limit: int = 50, offset: int = 0, payload: dict = Depends(get_current_payload)):
    if payload.get("platform_role") != "superadmin":
        raise HTTPException(status_code=403, detail={"error": {"code": "insufficient_role", "message": "SuperAdmin only.", "details": {}}})
    return await list_accounts(search, limit, offset)


@router.get("/accounts/{account_id}/overview", response_model=AccountOverview)
async def account_overview(account_id: str, payload: dict = Depends(get_current_payload)):
    require_admin_access(account_id, payload)
    profile, balance, usage = await get_account_profile(account_id), await get_credit_balance(account_id), await get_usage_summary(account_id)
    return AccountOverview(
        account_id=account_id,
        plan_tier=profile["plan_tier"],
        seat_count=profile["seat_count"],
        credit_balance=balance["balance"],
        usage_tokens_this_period=usage["total_tokens"],
        usage_cost_cents_this_period=usage["total_cost_cents"],
    )


@router.get("/audit-log", response_model=list[AuditLogEntry])
def audit_log(
    account_id: str | None = None,
    event_type: str | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    if payload.get("platform_role") != "superadmin":
        # TenantAdmin: force-scope to their own account_id regardless of
        # what (if anything) they passed in the query string.
        if payload.get("role") not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail={"error": {"code": "insufficient_role", "message": "Admin access required.", "details": {}}})
        account_id = payload.get("account_id")

    q = db.query(AuditLog)
    if account_id:
        q = q.filter(AuditLog.account_id == account_id)
    if event_type:
        q = q.filter(AuditLog.event_type == event_type)
    if from_:
        q = q.filter(AuditLog.occurred_at >= from_)
    if to:
        q = q.filter(AuditLog.occurred_at <= to)
    return q.order_by(AuditLog.occurred_at.desc()).limit(500).all()