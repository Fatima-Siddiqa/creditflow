import time

from fastapi import HTTPException, status

from app.config import settings
from app.redis_client import redis_client


def _too_many_requests(max_requests: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "error": {
                "code": "rate_limit_exceeded",
                "message": f"Too many requests. Limit is {max_requests} per {settings.rate_limit_window_seconds}s.",
                "details": {},
            }
        },
    )


def _check_limit(key_prefix: str, identifier: str, max_requests: int) -> None:
    """Sliding-window counter (per spec §8 Service 1: "token-bucket or
    sliding-window counters") — NOT a plain fixed-window counter, which
    has a known flaw: a client could send `max_requests` right before a
    window boundary and another `max_requests` right after, briefly
    getting ~2x the intended rate.

    Approach: track two adjacent fixed windows (current + previous) via
    INCR+EXPIRE, then estimate the true sliding count as a weighted blend
    of both — weighting the previous window down as the current one
    progresses. This is the standard "sliding window counter" algorithm:
    cheap (two INCRs, no sorted sets / request logs), and accurate enough
    that the boundary-burst problem above is no longer possible.
    """
    window_seconds = settings.rate_limit_window_seconds
    now = time.time()
    current_window = int(now // window_seconds)
    previous_window = current_window - 1

    current_key = f"ratelimit:{key_prefix}:{identifier}:{current_window}"
    previous_key = f"ratelimit:{key_prefix}:{identifier}:{previous_window}"

    current_count = redis_client.incr(current_key)
    if current_count == 1:
        # Keep it alive for two full windows — this same key is read as
        # "the previous window" during the window right after this one.
        redis_client.expire(current_key, window_seconds * 2)

    previous_count_raw = redis_client.get(previous_key)
    previous_count = int(previous_count_raw) if previous_count_raw is not None else 0

    # Fraction of the current window that has already elapsed — as this
    # approaches 1, the previous window's contribution fades to ~0.
    elapsed_fraction = (now % window_seconds) / window_seconds
    weighted_previous = previous_count * (1 - elapsed_fraction)

    estimated_count = current_count + weighted_previous

    if estimated_count > max_requests:
        raise _too_many_requests(max_requests)


def enforce_ip_rate_limit(client_ip: str) -> None:
    """Runs on every request, authenticated or not — the blanket defense
    against pure floods (including against the public auth routes, which
    have no account_id to key off of yet)."""
    _check_limit("ip", client_ip, settings.rate_limit_max_requests_per_ip)


def enforce_account_rate_limit(account_id: str) -> None:
    """Only callable once a token has been verified — this is what
    actually prevents one compromised or misbehaving account from
    drowning out others, independent of how many IPs it's coming from."""
    _check_limit("account", account_id, settings.rate_limit_max_requests_per_account)