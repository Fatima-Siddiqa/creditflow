import asyncio

from app.celery_app import celery_app
from app.db import SessionLocal
from app.events.publisher import publish_event
from app.firing import fire_due_schedules_once
from app.redis_client import lock_redis_client


def _publish_event_sync(event_type: str, payload: dict, account_id: str) -> None:
    """Celery tasks are sync; publish_event is async -- bridge with a
    fresh event loop per call, same as any sync-context caller of an
    async function with no surrounding loop already running."""
    asyncio.run(publish_event(event_type, payload, account_id))


@celery_app.task(name="app.tasks.fire_due_schedules")
def fire_due_schedules() -> list[str]:
    db = SessionLocal()
    try:
        return fire_due_schedules_once(db, lock_redis_client, _publish_event_sync)
    finally:
        db.close()