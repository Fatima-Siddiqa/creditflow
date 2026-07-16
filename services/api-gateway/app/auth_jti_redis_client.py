import redis

from app.config import settings

# Read-only. This is auth-service's store, not the gateway's — the gateway
# only ever calls .exists() on it, never .set()/.delete(). Kept as its own
# client (rather than reusing redis_client with a different db= per call)
# so that boundary is obvious at every call site.
auth_jti_redis_client = redis.Redis.from_url(settings.auth_jti_redis_url, decode_responses=True)