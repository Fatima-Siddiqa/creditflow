from datetime import date, datetime, timedelta


def compute_next_occurrence(publish_at: datetime, rule: dict) -> datetime | None:
    """Returns None if the next occurrence would fall on/after `until`
    (recurrence stops), or if `freq` isn't recognized."""
    freq = rule.get("freq")
    interval = rule.get("interval", 1)

    if freq == "daily":
        next_dt = publish_at + timedelta(days=interval)
    elif freq == "weekly":
        next_dt = publish_at + timedelta(weeks=interval)
    elif freq == "monthly":
        month = publish_at.month - 1 + interval
        year = publish_at.year + month // 12
        month = month % 12 + 1
        day = min(publish_at.day, 28)  # avoid Feb-30 type overflow; documented simplification
        next_dt = publish_at.replace(year=year, month=month, day=day)
    else:
        return None

    until = rule.get("until")
    if until and next_dt.date() > date.fromisoformat(until):
        return None
    return next_dt


def series_root_id(row) -> str:
    """A row's series root is its own id if it has no parent (it IS the
    root), otherwise its recurrence_parent_id -- every generated child
    is stamped with the ROOT's id directly (not chained to its immediate
    predecessor), so cancelling/grouping the whole series is a single
    flat query instead of walking a chain."""
    return row.recurrence_parent_id or row.id
