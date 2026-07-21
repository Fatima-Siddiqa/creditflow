import redis

from app.config import settings

# Read-only. This is auth-service's jti store (index 1), not this
# service's own state.
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

# PR #3: this service's own state, index 3 (shared with api-gateway's
# subscriber side -- see docs/CONVENTIONS.md's Redis logical DB index
# table and api-gateway/app/api/sse.py). A plain synchronous client is
# deliberate, not an oversight: PUBLISH is a single fire-and-forget
# round trip, and the rest of this service already calls Redis
# synchronously from async code paths (see app/dependencies.py's
# verify_access_token) rather than maintaining two client flavors.
sse_redis_client = redis.Redis.from_url(settings.sse_redis_url, decode_responses=True)