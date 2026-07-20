import uuid

from app.models.generation import GenerationJob, GenerationStatus


def test_generate_streams_tokens_end_to_end_through_redis(
    client, auth_headers, mock_quota_allowed, mock_openrouter_stream, test_redis_client, monkeypatch,
):
    """Exercises the real integration point (PR #3's actual change):
    POST /ai/generate schedules app.generation_worker.run_generation_stream
    as a real asyncio task, not just that the worker function works in
    isolation (already covered by tests/test_generation_worker.py).

    uuid.uuid4 is pinned so the test can subscribe to the exact
    sse:<job_id> channel *before* the request is made -- avoiding a race
    against a fake stream that (unlike a real OpenRouter call) completes
    almost instantly."""
    fixed_job_id = "11111111-1111-1111-1111-111111111111"
    monkeypatch.setattr("app.api.generation.uuid.uuid4", lambda: uuid.UUID(fixed_job_id))
    mock_openrouter_stream(["Hel", "lo"])

    pubsub = test_redis_client.pubsub()
    pubsub.subscribe(f"sse:{fixed_job_id}")
    pubsub.get_message(timeout=1)  # subscribe confirmation

    response = client.post("/ai/generate", json={"prompt": "hi"}, headers=auth_headers())
    assert response.status_code == 202
    assert response.json()["job_id"] == fixed_job_id

    received = []
    for _ in range(20):
        msg = pubsub.get_message(timeout=1)
        if msg and msg["type"] == "message":
            received.append(msg["data"])
        if received and received[-1] == "[DONE]":
            break
    pubsub.unsubscribe(f"sse:{fixed_job_id}")

    assert received == ["Hel", "lo", "[DONE]"]


def test_generate_job_row_persisted_by_direct_worker_call(
    client, auth_headers, mock_quota_allowed, mock_openrouter_stream, db_session,
):
    """PR #3 had a placeholder test here asserting generation_jobs.status
    stayed RUNNING after the stream finished, self-documented as "should
    start failing once PR #4 lands." It wouldn't have: the real
    background task (app.generation_worker.run_generation_stream) opens
    its OWN SessionLocal() connection, which -- under this project's
    SAVEPOINT-based test isolation (see the db_session fixture in
    conftest.py) -- can never see a row this test's own transaction
    hasn't actually committed to Postgres. Keeping that test would have
    kept "passing" after PR #4 for the wrong reason, proving nothing
    about the new persistence logic.

    The real persistence assertions now live in
    tests/test_generation_persistence.py, calling
    app.generation_worker._run_generation_stream_core(db_session, ...)
    directly so the worker's writes and the test's reads share the same
    transaction. This test just confirms POST /ai/generate's own,
    request-scoped write (the RUNNING row) is visible right after the
    call returns -- unaffected by PR #4, still worth keeping."""
    mock_openrouter_stream(["hi"])
    response = client.post("/ai/generate", json={"prompt": "hi"}, headers=auth_headers())
    job_id = response.json()["job_id"]

    job = db_session.query(GenerationJob).filter(GenerationJob.id == job_id).one()
    assert job.status == GenerationStatus.RUNNING