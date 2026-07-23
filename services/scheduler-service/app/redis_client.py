import redis

from app.config import settings

# Read-only. Auth-service's jti store (index 1).
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

# This service's own Celery broker db (index 2) -- reused here for the
# double-fire SETNX lock in app/firing.py, since it's already scheduler's
# own Redis logical db, not borrowed from another service.
lock_redis_client = redis.Redis.from_url(settings.celery_redis_url, decode_responses=True)