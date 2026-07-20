import asyncio
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.usage import UsageLedger
from app.period import get_current_period, period_bounds, seconds_until_period_end
from app.usage_redis import usage_redis_client

logger = logging.getLogger("reconciliation")


def _usage_key(account_id: str, period: str) -> str:
    return f"usage:{account_id}:{period}"


def reconcile_account(db: Session, redis_client, account_id: str, period: str) -> int:
    """Recomputes one account's counter straight from usage_ledger (the
    source of truth) and overwrites Redis with it -- this is the only
    correct direction to reconcile in; the ledger is never adjusted to
    match Redis. Returns the corrected total, so callers/tests can assert
    on it directly without a second read."""
    start, end = period_bounds(period)
    total = (
        db.query(func.coalesce(func.sum(UsageLedger.tokens_used), 0))
        .filter(UsageLedger.account_id == account_id, UsageLedger.created_at >= start, UsageLedger.created_at < end)
        .scalar()
    )
    total = int(total or 0)
    redis_client.set(_usage_key(account_id, period), total, ex=seconds_until_period_end(period))
    return total


def reconcile_all_active_accounts(db: Session, redis_client, period: str | None = None) -> int:
    """'Active' = has at least one usage_ledger row this period. Accounts
    that used nothing this period have no drift to correct -- a missing
    Redis key already reads back as 0 via check_quota's `or 0`, so
    reconciling them would be a no-op write anyway."""
    period = period or get_current_period()
    start, end = period_bounds(period)
    account_ids = [
        row[0]
        for row in db.query(UsageLedger.account_id)
        .filter(UsageLedger.created_at >= start, UsageLedger.created_at < end)
        .distinct()
        .all()
    ]
    for account_id in account_ids:
        reconcile_account(db, redis_client, account_id, period)
    return len(account_ids)


async def run_reconciliation_loop() -> None:
    """Runs forever as a background task from app.main's lifespan (same
    pattern as app.events.ai_consumer.run_consumer). A plain sleep loop,
    not Celery -- Celery/Celery Beat is scoped to scheduler-service
    (Phase 10) per spec §3's technology table, so this service doesn't
    take on a second task-queue dependency just for one periodic job.
    Interval is configurable via RECONCILIATION_INTERVAL_SECONDS
    (default 300s / 5min) -- see Phase 7 plan's 'every N minutes... pick
    one and document why': 5 minutes bounds worst-case Redis drift to a
    short window without hammering Postgres with a full-table scan every
    few seconds."""
    while True:
        await asyncio.sleep(settings.reconciliation_interval_seconds)
        db = SessionLocal()
        try:
            count = await asyncio.to_thread(reconcile_all_active_accounts, db, usage_redis_client)
            logger.info("reconciliation pass complete: %d account(s) corrected", count)
        except Exception:
            logger.exception("reconciliation loop pass failed, will retry next interval")
        finally:
            db.close()
