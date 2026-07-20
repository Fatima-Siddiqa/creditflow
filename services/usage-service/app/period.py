from datetime import datetime, timezone


def get_current_period() -> str:
    """'YYYY-MM' in UTC. This is the one and only definition of 'billing
    period' this service uses -- Redis counter keys, the threshold-
    notification uniqueness constraint, and the ledger-based summary/
    reconciliation queries all key off this exact string. Never recompute
    'current period' a second, slightly different way anywhere else in
    this service."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def period_bounds(period: str) -> tuple[datetime, datetime]:
    """[start, end) in UTC for a 'YYYY-MM' period string."""
    year, month = (int(p) for p in period.split("-"))
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


def seconds_until_period_end(period: str | None = None) -> int:
    """Redis TTL for a usage counter key -- aligns expiry to the billing
    period reset, per the Phase 7 plan ('TTL aligned to billing period
    reset'), so an orphaned key can never silently outlive its period.
    Floored at 60s so a key created in the last minute of a period doesn't
    get an effectively-zero (or negative, which redis-py rejects) TTL."""
    period = period or get_current_period()
    _, end = period_bounds(period)
    now = datetime.now(timezone.utc)
    return max(int((end - now).total_seconds()), 60)
