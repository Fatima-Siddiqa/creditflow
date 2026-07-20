import redis

from app.config import settings

# Read-only. This is auth-service's jti store (index 1), not this
# service's own state -- this service owns no Redis state of its own
# until PR #3 adds SSE publishing (index 3, see app/config.py).
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)