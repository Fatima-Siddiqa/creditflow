import uuid

from app.models.social import PublishJob, PublishStatus


def _job(db, account_id="test_acc_123", scheduled_post_id=None, status=PublishStatus.PUBLISHED, urn="urn:li:share:1"):
    row = PublishJob(
        id=str(uuid.uuid4()),
        scheduled_post_id=scheduled_post_id or str(uuid.uuid4()),
        content_id=str(uuid.uuid4()),
        account_id=account_id,
        status=status,
        attempt_count=1,
        linkedin_post_urn=urn,
    )
    db.add(row)
    db.flush()
    return row


def test_requires_auth(client):
    res = client.get("/social/publish-jobs")
    assert res.status_code == 401


def test_lists_only_own_account_jobs(client, db_session, auth_headers):
    _job(db_session, account_id="test_acc_123")
    _job(db_session, account_id="other_account")
    db_session.commit()

    res = client.get("/social/publish-jobs", headers=auth_headers())
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["status"] == "published"
    assert body[0]["linkedin_post_urn"] == "urn:li:share:1"


def test_filters_by_scheduled_post_id(client, db_session, auth_headers):
    target = _job(db_session, scheduled_post_id="sched_1")
    _job(db_session, scheduled_post_id="sched_2")
    db_session.commit()

    res = client.get("/social/publish-jobs", params={"scheduled_post_id": "sched_1"}, headers=auth_headers())
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["id"] == target.id


def test_ordered_most_recent_first(client, db_session, auth_headers):
    import time
    first = _job(db_session)
    db_session.commit()
    time.sleep(0.01)
    second = _job(db_session)
    db_session.commit()

    res = client.get("/social/publish-jobs", headers=auth_headers())
    ids = [row["id"] for row in res.json()]
    assert ids.index(second.id) < ids.index(first.id)