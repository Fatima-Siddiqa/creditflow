from datetime import datetime, timedelta, timezone

from app.models.scheduled_post import ScheduledPost, ScheduleStatus


def _iso(dt):
    return dt.isoformat()


def _make_row(db_session, account_id="test_acc_123", status=ScheduleStatus.PENDING, publish_at=None, recurrence_rule=None, recurrence_parent_id=None, has_image=False):
    row = ScheduledPost(
        id=__import__("uuid").uuid4().hex, account_id=account_id, content_id="content-1", has_image=has_image,
        publish_at=publish_at or datetime.now(timezone.utc) + timedelta(days=1), status=status,
        recurrence_rule=recurrence_rule, recurrence_parent_id=recurrence_parent_id,
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_schedule_creates_pending_row(client, auth_headers):
    publish_at = datetime.now(timezone.utc) + timedelta(days=1)
    response = client.post("/scheduler", json={"content_id": "content-1", "publish_at": _iso(publish_at)}, headers=auth_headers())
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["has_image"] is False


def test_schedule_rejects_unapproved_content(client, auth_headers, monkeypatch):
    async def _fake(content_id, auth):
        return {"id": content_id, "status": "draft", "image_url": None}
    monkeypatch.setattr("app.api.scheduled_post.get_content", _fake)

    response = client.post("/scheduler", json={"content_id": "content-1", "publish_at": _iso(datetime.now(timezone.utc) + timedelta(days=1))}, headers=auth_headers())
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "content_not_approved"


def test_schedule_404_when_content_not_found(client, auth_headers, monkeypatch):
    async def _fake(content_id, auth):
        return None
    monkeypatch.setattr("app.api.scheduled_post.get_content", _fake)

    response = client.post("/scheduler", json={"content_id": "missing", "publish_at": _iso(datetime.now(timezone.utc) + timedelta(days=1))}, headers=auth_headers())
    assert response.status_code == 404


def test_schedule_requires_publish_role(client, auth_headers):
    response = client.post("/scheduler", json={"content_id": "content-1", "publish_at": _iso(datetime.now(timezone.utc) + timedelta(days=1))}, headers=auth_headers(role="member"))
    assert response.status_code == 403


def test_calendar_scopes_to_account_and_date_range(client, auth_headers, db_session):
    in_range = _make_row(db_session, publish_at=datetime.now(timezone.utc) + timedelta(days=2))
    _make_row(db_session, publish_at=datetime.now(timezone.utc) + timedelta(days=200))  # out of range
    _make_row(db_session, account_id="other_acc", publish_at=datetime.now(timezone.utc) + timedelta(days=2))  # other account

    frm = datetime.now(timezone.utc)
    to = frm + timedelta(days=10)
    response = client.get("/scheduler/calendar", params={"from": _iso(frm), "to": _iso(to)}, headers=auth_headers())
    assert response.status_code == 200
    ids = [r["id"] for r in response.json()]
    assert ids == [in_range.id]


def test_reschedule_updates_publish_at(client, auth_headers, db_session):
    row = _make_row(db_session)
    new_time = datetime.now(timezone.utc) + timedelta(days=5)
    response = client.patch(f"/scheduler/{row.id}/reschedule", json={"publish_at": _iso(new_time)}, headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["publish_at"][:19] == _iso(new_time)[:19]


def test_reschedule_404_for_other_account(client, auth_headers, db_session):
    row = _make_row(db_session, account_id="other_acc")
    response = client.patch(f"/scheduler/{row.id}/reschedule", json={"publish_at": _iso(datetime.now(timezone.utc))}, headers=auth_headers())
    assert response.status_code == 404


def test_cancel_single_does_not_touch_series(client, auth_headers, db_session):
    root = _make_row(db_session, recurrence_rule={"freq": "weekly", "interval": 1})
    response = client.delete(f"/scheduler/{root.id}", headers=auth_headers())
    assert response.status_code == 204

    rows = db_session.query(ScheduledPost).filter(ScheduledPost.account_id == "test_acc_123").all()
    assert len(rows) == 2  # original (cancelled) + spawned next occurrence
    statuses = {r.status for r in rows}
    assert statuses == {ScheduleStatus.CANCELLED, ScheduleStatus.PENDING}


def test_cancel_series_cancels_all_pending_occurrences(client, auth_headers, db_session):
    root = _make_row(db_session, recurrence_rule={"freq": "weekly", "interval": 1})
    _make_row(db_session, recurrence_parent_id=root.id, publish_at=datetime.now(timezone.utc) + timedelta(days=8))
    unrelated = _make_row(db_session)

    response = client.delete(f"/scheduler/{root.id}", params={"scope": "series"}, headers=auth_headers())
    assert response.status_code == 204

    db_session.refresh(root)
    assert root.status == ScheduleStatus.CANCELLED
    for row in db_session.query(ScheduledPost).filter(ScheduledPost.id != unrelated.id, ScheduledPost.id != root.id).all():
        assert row.status == ScheduleStatus.CANCELLED
    db_session.refresh(unrelated)
    assert unrelated.status == ScheduleStatus.PENDING
