import redis

from app.config import settings

# settings.redis_url already includes the logical DB index (/1), per
# CONVENTIONS.md — auth-service owns index 1 for its jti store and
# rate-limit counters.
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)