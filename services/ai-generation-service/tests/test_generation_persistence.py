import asyncio
import uuid

import pytest

from app.generation_worker import _run_generation_stream_core
from app.models.generation import GenerationJob, GenerationStatus, PromptHistory

pytestmark = pytest.mark.asyncio


def _make_job(db_session, account_id="acc_1", user_id="user_1", model="openai/gpt-4o-mini", prompt="say hi"):
    job_id = str(uuid.uuid4())
    db_session.add(GenerationJob(id=job_id, account_id=account_id, created_by_user_id=user_id, model=model, status=GenerationStatus.RUNNING))
    db_session.add(PromptHistory(id=str(uuid.uuid4()), job_id=job_id, account_id=account_id, prompt=prompt))
    db_session.commit()
    return job_id


async def _fake_stream_ok(model, prompt):
    for chunk in ["Cred", "its ", "flow ", "rocks."]:
        yield chunk


async def _fake_stream_error(model, prompt):
    from app.openrouter_client import OpenRouterError
    yield "partial"
    raise OpenRouterError("upstream exploded")


async def _fake_stream_hangs(model, prompt):
    yield "starting"
    await asyncio.sleep(10)
    yield "never reached"  # pragma: no cover


async def test_completed_job_persists_response_and_tokens(monkeypatch, db_session, captured_events):
    job_id = _make_job(db_session, account_id="acc_complete", prompt="say hi")
    monkeypatch.setattr("app.generation_worker.stream_chat_completion", _fake_stream_ok)
    monkeypatch.setattr("app.generation_worker.publish_token", lambda *a, **k: None)
    monkeypatch.setattr("app.generation_worker.publish_done", lambda *a, **k: None)

    await _run_generation_stream_core(db_session, job_id, "openai/gpt-4o-mini", "say hi")

    job = db_session.query(GenerationJob).filter(GenerationJob.id == job_id).one()
    assert job.status == GenerationStatus.COMPLETED
    assert job.completed_at is not None
    assert job.total_tokens == job.prompt_tokens + job.completion_tokens
    assert job.prompt_tokens > 0 and job.completion_tokens > 0
    assert job.cost_cents == 0  # documented placeholder -- see _estimate_tokens docstring

    history = db_session.query(PromptHistory).filter(PromptHistory.job_id == job_id).one()
    assert history.response == "Credits flow rocks."

    # Exactly one event, shaped to satisfy usage-service's already-live
    # consumer contract (payload["tokens_used"] is REQUIRED there --
    # see app/events/publisher.py's docstring).
    assert len(captured_events) == 1
    event_type, payload, account_id = captured_events[0]
    assert event_type == "ai.generation_completed"
    assert account_id == "acc_complete"
    assert payload["account_id"] == "acc_complete"
    assert payload["model"] == "openai/gpt-4o-mini"
    assert payload["tokens_used"] == job.total_tokens
    assert payload["cost_cents"] == 0
    assert payload["prompt_tokens"] == job.prompt_tokens
    assert payload["completion_tokens"] == job.completion_tokens


async def test_failed_job_persists_error_reason_and_publishes_failed_event(monkeypatch, db_session, captured_events):
    job_id = _make_job(db_session, account_id="acc_fail")
    monkeypatch.setattr("app.generation_worker.stream_chat_completion", _fake_stream_error)
    monkeypatch.setattr("app.generation_worker.publish_token", lambda *a, **k: None)
    published_errors = []
    monkeypatch.setattr("app.generation_worker.publish_error", lambda job_id, reason: published_errors.append(reason))

    await _run_generation_stream_core(db_session, job_id, "openai/gpt-4o-mini", "hi")

    job = db_session.query(GenerationJob).filter(GenerationJob.id == job_id).one()
    assert job.status == GenerationStatus.FAILED
    assert "upstream exploded" in job.error_reason
    assert job.completed_at is not None

    # No response ever gets written for a failed job.
    history = db_session.query(PromptHistory).filter(PromptHistory.job_id == job_id).one()
    assert history.response is None

    assert published_errors == ["upstream exploded"]
    assert len(captured_events) == 1
    event_type, payload, account_id = captured_events[0]
    assert event_type == "ai.generation_failed"
    assert account_id == "acc_fail"
    assert payload["reason"] == "upstream exploded"


async def test_cancelled_job_persists_status_but_publishes_no_ai_event(monkeypatch, db_session, captured_events):
    job_id = _make_job(db_session, account_id="acc_cancel")
    monkeypatch.setattr("app.generation_worker.stream_chat_completion", _fake_stream_hangs)
    monkeypatch.setattr("app.generation_worker.publish_token", lambda *a, **k: None)

    task = asyncio.create_task(_run_generation_stream_core(db_session, job_id, "openai/gpt-4o-mini", "stall"))
    await asyncio.sleep(0.05)  # let it publish "starting" and reach the sleep
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    job = db_session.query(GenerationJob).filter(GenerationJob.id == job_id).one()
    assert job.status == GenerationStatus.CANCELLED
    assert job.completed_at is not None

    # PR #5's contract: cancellation publishes nothing to ai_events.
    assert captured_events == []


async def test_completion_of_a_job_with_no_matching_db_row_does_not_crash(monkeypatch, db_session, captured_events):
    """Defensive case: the worker is called for a job_id that was never
    persisted (shouldn't happen via POST /generate, but several existing
    tests in tests/test_generation_worker.py call the worker directly
    with made-up job_ids like "job-order-1"). Should complete without
    raising, just skip the DB writes."""
    monkeypatch.setattr("app.generation_worker.stream_chat_completion", _fake_stream_ok)
    monkeypatch.setattr("app.generation_worker.publish_token", lambda *a, **k: None)
    monkeypatch.setattr("app.generation_worker.publish_done", lambda *a, **k: None)

    await _run_generation_stream_core(db_session, "no-such-job", "openai/gpt-4o-mini", "hi")

    assert db_session.query(GenerationJob).filter(GenerationJob.id == "no-such-job").one_or_none() is None
    assert len(captured_events) == 1
    event_type, payload, account_id = captured_events[0]
    assert event_type == "ai.generation_completed"
    assert account_id is None
    assert payload["account_id"] is None