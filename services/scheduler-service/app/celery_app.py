from celery import Celery

from app.config import settings

celery_app = Celery("scheduler", broker=settings.celery_redis_url, backend=settings.celery_redis_url)
celery_app.conf.beat_schedule = {
    "fire-due-schedules": {"task": "app.tasks.fire_due_schedules", "schedule": settings.beat_interval_seconds},
}
celery_app.conf.timezone = "UTC"

import app.tasks  # noqa: E402,F401  (registers the task with celery_app)
