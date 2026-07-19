import redis

from app.config import settings

# Index 0 per CONVENTIONS.md: "0 = gateway rate-limit/webhook-dedup"
webhook_dedup_redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)