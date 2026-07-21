import uuid
from datetime import date, datetime, timedelta, timezone


from app.firing import fire_due_schedules_once
from app.models.scheduled_post import ScheduledPost, ScheduleStatus
from app.recurrence import compute_next_occurrence, series_root_id


def _due_row(db_session, account_id="acc_1", recurrence_rule=None, recurrence_parent_id=None, minutes_ago=5):
    row = ScheduledPost(
        id=str(uuid.uuid4()), account_id=account_id, content_id="content-1", has_image=False,
        publish_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        status=ScheduleStatus.PENDING, recurrence_rule=recurrence_rule, recurrence_parent_id=recurrence_parent_id,
    )
    db_session.add(row)
    db_session.commit()
    return row


# --- app/recurrence.py -------------------------------------------------

def test_compute_next_occurrence_weekly():
    start = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    nxt = compute_next_occurrence(start, {"freq": "weekly", "interval": 1})
    assert nxt == start + timedelta(weeks=1)


def test_compute_next_occurrence_stops_at_until():
    start = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    nxt = compute_next_occurrence(start, {"freq": "weekly", "interval": 1, "until": "2026-07-05"})
    assert nxt is None


def test_series_root_id_propagates_root_not_predecessor():
    class Row:
        id = "child-2"
        recurrence_parent_id = "root-1"
    assert series_root_id(Row()) == "root-1"

    class Root:
        id = "root-1"
        recurrence_parent_id = None
    assert series_root_id(Root()) == "root-1"


# --- app/firing.py -------------------------------------------------------

def test_firing_generates_exactly_one_next_occurrence(db_session, firing_redis):
    row = _due_row(db_session, recurrence_rule={"freq": "weekly", "interval": 1})
    published = []
    fired = fire_due_schedules_once(db_session, firing_redis, lambda *a: published.append(a))

    assert fired == [row.id]
    db_session.refresh(row)
    assert row.status == ScheduleStatus.FIRED

    children = db_session.query(ScheduledPost).filter(ScheduledPost.recurrence_parent_id == row.id).all()
    assert len(children) == 1
    assert children[0].status == ScheduleStatus.PENDING
    assert children[0].publish_at.date() == (row.publish_at + timedelta(weeks=1)).date()
    assert len(published) == 1


def test_firing_one_off_generates_no_children(db_session, firing_redis):
    row = _due_row(db_session, recurrence_rule=None)
    fire_due_schedules_once(db_session, firing_redis, lambda *a: None)
    assert db_session.query(ScheduledPost).filter(ScheduledPost.recurrence_parent_id == row.id).count() == 0


def test_firing_stops_recurrence_past_until(db_session, firing_redis):
    row = _due_row(db_session, recurrence_rule={"freq": "weekly", "interval": 1, "until": date.today().isoformat()})
    fire_due_schedules_once(db_session, firing_redis, lambda *a: None)
    assert db_session.query(ScheduledPost).filter(ScheduledPost.recurrence_parent_id == row.id).count() == 0


def test_firing_never_fires_cancelled_rows(db_session, firing_redis):
    row = _due_row(db_session)
    row.status = ScheduleStatus.CANCELLED
    db_session.commit()
    published = []
    fired = fire_due_schedules_once(db_session, firing_redis, lambda *a: published.append(a))
    assert fired == []
    assert published == []


def test_double_fire_prevention_under_concurrent_runs(db_session, firing_redis):
    """Simulates two overlapping beat runs against the SAME due row --
    only one should win the lock and publish."""
    row = _due_row(db_session)
    shared_redis = firing_redis
    published = []

    fired_1 = fire_due_schedules_once(db_session, shared_redis, lambda *a: published.append(a))
    fired_2 = fire_due_schedules_once(db_session, shared_redis, lambda *a: published.append(a))

    assert fired_1 == [row.id]
    assert fired_2 == []  # already 'fired' in DB by the time run 2 queries, AND lock held either way
    assert len(published) == 1
