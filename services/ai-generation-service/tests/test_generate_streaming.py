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


def test_generate_job_row_still_running_after_stream_since_pr4_not_landed(
    client, auth_headers, mock_quota_allowed, mock_openrouter_stream, test_redis_client, db_session,
):
    """Documents current, intentional PR #3 scope: streaming finishing
    does NOT flip generation_jobs.status (that's PR #4). If this test
    starts failing because status flips to completed, PR #4's
    persistence step landed in the wrong branch."""
    mock_openrouter_stream(["hi"])

    response = client.post("/ai/generate", json={"prompt": "hi"}, headers=auth_headers())
    job_id = response.json()["job_id"]

    pubsub = test_redis_client.pubsub()
    pubsub.subscribe(f"sse:{job_id}")
    msg = pubsub.get_message(timeout=1)
    while msg and msg["type"] != "message":
        msg = pubsub.get_message(timeout=2)  # wait for [DONE] -- confirms the stream actually ran
    pubsub.unsubscribe(f"sse:{job_id}")

    job = db_session.query(GenerationJob).filter(GenerationJob.id == job_id).one()
    assert job.status == GenerationStatus.RUNNING