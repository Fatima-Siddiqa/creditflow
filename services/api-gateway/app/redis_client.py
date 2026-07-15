import redis

from app.config import settings

# settings.redis_url already includes the logical DB index (/0), per
# CONVENTIONS.md — api-gateway owns index 0 for rate-limit counters,
# webhook dedup keys, and SSE channel subscriptions.
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)