import redis

from app.config import settings

# Read-only. Auth-service's jti store (index 1).
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)