from app.config import settings
from app.redis_client import redis_client


def is_duplicate_event(event_id: str) -> bool:
    """Returns True if this event_id has already been seen (caller should
    skip reprocessing), False on first sight (in which case the dedup key
    is now set, so a redelivery of the same event_id correctly returns
    True from here on until the TTL expires).

    SET key val NX EX ttl is atomic — no separate GET-then-SET race."""
    was_set = redis_client.set(f"webhook:{event_id}", "1", nx=True, ex=settings.webhook_dedup_ttl_seconds)
    return not was_set