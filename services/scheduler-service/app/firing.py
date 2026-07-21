import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.api.scheduled_post import _spawn_next_occurrence
from app.models.scheduled_post import ScheduledPost, ScheduleStatus

logger = logging.getLogger("firing")

LOCK_TTL_SECONDS = 120


def fire_due_schedules_once(db: Session, redis_client, publish_event_sync) -> list[str]:
    """Selects due PENDING rows, fires each under a Redis lock (SETNX)
    keyed on row id -- guards the SELECT-then-UPDATE window between two
    overlapping beat ticks/workers picking up the SAME row before either
    commits status='fired'. Returns the list of fired row ids.

    publish_event_sync: a sync callable(event_type, payload, account_id)
    -- app/tasks.py passes a wrapper around the async publish_event
    (Celery tasks are sync); tests pass a plain list-appending stub.
    Never called for a row that loses the lock race.
    """
    now = datetime.now(timezone.utc)
    due = db.query(ScheduledPost).filter(ScheduledPost.status == ScheduleStatus.PENDING, ScheduledPost.publish_at <= now).all()

    fired: list[str] = []
    for row in due:
        lock_key = f"schedule_lock:{row.id}"
        if not redis_client.set(lock_key, "1", nx=True, ex=LOCK_TTL_SECONDS):
            continue  # another concurrent beat run already has this row

        row.status = ScheduleStatus.FIRED
        _spawn_next_occurrence(db, row)
        db.commit()

        try:
            publish_event_sync(
                "content.scheduled",
                {"schedule_id": row.id, "content_id": row.content_id, "account_id": row.account_id, "has_image": row.has_image},
                row.account_id,
            )
        except Exception:
            logger.exception("fired schedule %s but failed to publish content.scheduled", row.id)
        fired.append(row.id)

    return fired
