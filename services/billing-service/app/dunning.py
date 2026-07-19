import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal
from app.models import OutboxEvent, Subscription

logger = logging.getLogger("billing.dunning")


def _check_overdue_subscriptions():
    db = SessionLocal()
    try:
        overdue = (
            db.query(Subscription)
            .filter(Subscription.status == "past_due", Subscription.grace_period_ends_at < datetime.now(timezone.utc))
            .all()
        )
        for sub in overdue:
            sub.status = "downgraded"
            sub.plan_tier = "free"
            sub.grace_period_ends_at = None
            db.add(OutboxEvent(event_type="subscription.downgraded", payload={"account_id": str(sub.account_id)}, account_id=sub.account_id))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("dunning check cycle failed")
    finally:
        db.close()


async def run_dunning_checker():
    while True:
        await asyncio.to_thread(_check_overdue_subscriptions)
        await asyncio.sleep(settings.dunning_check_interval_seconds)