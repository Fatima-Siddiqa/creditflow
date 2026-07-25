import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db import recurring_jobs
from app.events.publisher import publish_event

logger = logging.getLogger("recurring_loop")


async def _tick() -> None:
    now = datetime.now(timezone.utc)
    due = recurring_jobs.find({"next_run_at": {"$lte": now.isoformat()}, "active": True})
    for job in due:
        try:
            await publish_event("scrape.requested", {
                "job_id": None,
                "account_id": job.get("account_id"),
                "target_url": job["target_url"],
                "job_type": job.get("job_type", "recurring"),
            }, account_id=job.get("account_id"))
        except Exception:
            logger.exception("failed to fire recurring job %s", job["_id"])
            continue
        next_run = now + timedelta(seconds=job["interval_seconds"])
        recurring_jobs.update_one({"_id": job["_id"]}, {"$set": {"next_run_at": next_run.isoformat(), "last_fired_at": now.isoformat()}})


async def run_recurring_loop() -> None:
    """Simple asyncio-loop scheduler (per PHASE_12 note: this service
    doesn't need Celery Beat's lock/outbox sophistication -- re-scraping
    isn't destructive, so an occasional double-fire on restart is
    acceptable here, unlike Scheduler Service's publish scheduling)."""
    while True:
        await _tick()
        await asyncio.sleep(settings.recurring_scan_interval_seconds)