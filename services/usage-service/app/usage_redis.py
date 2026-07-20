import redis

from app.config import settings

# This service's OWN live state -- logical Redis DB index 4 per
# docs/CONVENTIONS.md. Unlike app/redis_client.py (read-only access to
# auth-service's jti store), this one is read-write: usage-service is the
# sole owner/writer of these counters.
usage_redis_client = redis.Redis.from_url(settings.usage_redis_url, decode_responses=True)


def get_usage_redis():
    """FastAPI dependency wrapper so tests can override this via
    app.dependency_overrides, the same pattern already used for app.db.get_db
    -- avoids monkeypatching a module-level attribute for anything reached
    through HTTP endpoints."""
    return usage_redis_client
