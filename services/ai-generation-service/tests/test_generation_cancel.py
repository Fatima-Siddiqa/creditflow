import asyncio
import uuid

import pytest

from app import job_registry
from app.generation_worker import _run_generation_stream_core
from app.models.generation import GenerationJob, GenerationStatus, PromptHistory

pytestmark = pytest.mark.asyncio


def _make_job(db_session, account_id="acc_1", user_id="user_1", model="openai/gpt-4o-mini", prompt="say hi", status=GenerationStatus.RUNNING):
    job_id = str(uuid.uuid4())
    db_session.add(GenerationJob(id=job_id, account_id=account_id, created_by_user_id=user_id, model=model, status=status))
    db_session.add(PromptHistory(id=str(uuid.uuid4()), job_id=job_id, account_id=account_id, prompt=prompt))
    db_session.commit()
    return job_id


async def test_cancel_returns_404_for_unknown_job(client, auth_headers):
    response = client.post(f"/ai/generate/{uuid.uuid4()}/cancel", headers=auth_headers())
    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "job_not_found"


async def test_cancel_returns_404_for_someone_elses_job(client, auth_headers, db_session):
    """Same 404 (not 403) as the unknown-job case -- this endpoint can't
    be used to distinguish 'doesn't exist' from 'exists but isn't
    yours' by probing status codes."""
    job_id = _make_job(db_session, account_id="acc_owner")

    response = client.post(f"/ai/generate/{job_id}/cancel", headers=auth_headers(account_id="acc_intruder"))
    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "job_not_found"


async def test_cancel_returns_409_when_job_already_completed(client, auth_headers, db_session):
    job_id = _make_job(db_session, account_id="acc_done", status=GenerationStatus.COMPLETED)

    response = client.post(f"/ai/generate/{job_id}/cancel", headers=auth_headers(account_id="acc_done"))
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "job_not_running"


async def test_cancel_returns_409_when_already_cancelled(client, auth_headers, db_session):
    job_id = _make_job(db_session, account_id="acc_done2", status=GenerationStatus.CANCELLED)

    response = client.post(f"/ai/generate/{job_id}/cancel", headers=auth_headers(account_id="acc_done2"))
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "job_not_running"


async def test_cancel_returns_409_when_running_in_db_but_not_registered(client, auth_headers, db_session):
    """Row says RUNNING but there's no matching asyncio.Task in
    job_registry (e.g. this worker process restarted since the job
    started) -- must not silently report success for a cancel that
    didn't actually stop anything."""
    job_id = _make_job(db_session, account_id="acc_orphan")

    response = client.post(f"/ai/generate/{job_id}/cancel", headers=auth_headers(account_id="acc_orphan"))
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "job_not_running"


async def test_cancel_stops_a_genuinely_running_task(client, auth_headers, db_session, monkeypatch):
    job_id = _make_job(db_session, account_id="acc_live")

    async def _slow_stream(model, prompt):
        yield "first "
        await asyncio.sleep(5)
        yield "unreachable"  # pragma: no cover

    monkeypatch.setattr("app.generation_worker.stream_chat_completion", _slow_stream)
    monkeypatch.setattr("app.generation_worker.publish_token", lambda *a, **k: None)

    # Runs _run_generation_stream_core directly against THIS test's own
    # db_session, same as tests/test_generation_persistence.py -- the
    # real run_generation_stream() wrapper opens its own separate
    # SessionLocal() connection, which can't see this test's uncommitted
    # savepoint, so its _mark_cancelled would silently find no row to
    # update. This still exercises the real thing PR #5 needs to prove:
    # the HTTP endpoint finding job_registry's task and calling
    # task.cancel() on it.
    task = asyncio.create_task(_run_generation_stream_core(db_session, job_id, "openai/gpt-4o-mini", "stall"))
    job_registry.register(job_id, task)
    try:
        await asyncio.sleep(0.05)  # let it publish "first " and reach the sleep

        response = client.post(f"/ai/generate/{job_id}/cancel", headers=auth_headers(account_id="acc_live"))
        assert response.status_code == 202
        assert response.json() == {"job_id": job_id, "status": "cancelling"}

        with pytest.raises(asyncio.CancelledError):
            await task

        job = db_session.query(GenerationJob).filter(GenerationJob.id == job_id).one()
        assert job.status == GenerationStatus.CANCELLED
    finally:
        # _run_generation_stream_core doesn't discard from job_registry
        # itself -- run_generation_stream()'s `finally` does that (see
        # app/generation_worker.py) -- so this test cleans up after
        # itself the way that wrapper normally would.
        job_registry.discard(job_id)


async def test_cancel_requires_auth(client):
    response = client.post(f"/ai/generate/{uuid.uuid4()}/cancel")
    assert response.status_code == 401
