import asyncio

import pytest

from app import job_registry
from app.generation_worker import run_generation_stream

pytestmark = pytest.mark.asyncio


async def test_worker_publishes_tokens_in_order_then_done(mock_openrouter_stream, test_redis_client):
    mock_openrouter_stream(["Once ", "upon ", "a ", "time"])

    pubsub = test_redis_client.pubsub()
    pubsub.subscribe("sse:job-order-1")
    pubsub.get_message(timeout=1)  # consume the subscribe confirmation

    await run_generation_stream(job_id="job-order-1", model="openai/gpt-4o-mini", prompt="hi")

    received = []
    for _ in range(10):
        msg = pubsub.get_message(timeout=1)
        if msg and msg["type"] == "message":
            received.append(msg["data"])
        if received and received[-1] == "[DONE]":
            break
    pubsub.unsubscribe("sse:job-order-1")

    assert received == ["Once ", "upon ", "a ", "time", "[DONE]"]


async def test_worker_publishes_error_sentinel_on_openrouter_failure(mock_openrouter_error, test_redis_client):
    mock_openrouter_error("OpenRouter timed out")

    pubsub = test_redis_client.pubsub()
    pubsub.subscribe("sse:job-error-1")
    pubsub.get_message(timeout=1)

    await run_generation_stream(job_id="job-error-1", model="openai/gpt-4o-mini", prompt="hi")

    msg = pubsub.get_message(timeout=1)
    while msg and msg["type"] != "message":
        msg = pubsub.get_message(timeout=1)
    pubsub.unsubscribe("sse:job-error-1")

    assert msg is not None
    assert msg["data"] == "[ERROR] OpenRouter timed out"


async def test_worker_discards_registry_entry_after_stream_ends(mock_openrouter_stream):
    mock_openrouter_stream(["hi"])
    # Placeholder value -- run_generation_stream's `finally` clears by
    # job_id key, not by task identity, so a real Task isn't needed here.
    job_registry.register("job-cleanup-1", object())

    await run_generation_stream(job_id="job-cleanup-1", model="openai/gpt-4o-mini", prompt="hi")

    assert job_registry.get("job-cleanup-1") is None


async def test_worker_cancellation_stops_without_publishing_done_or_error(test_redis_client, monkeypatch):
    async def _slow_stream(model, prompt):
        yield "first "
        await asyncio.sleep(5)
        yield "unreachable"  # pragma: no cover

    monkeypatch.setattr("app.generation_worker.stream_chat_completion", _slow_stream)

    pubsub = test_redis_client.pubsub()
    pubsub.subscribe("sse:job-cancel-1")
    pubsub.get_message(timeout=1)

    task = asyncio.create_task(
        run_generation_stream(job_id="job-cancel-1", model="openai/gpt-4o-mini", prompt="hi")
    )
    await asyncio.sleep(0.05)  # let it publish "first " and reach the sleep
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    received = []
    msg = pubsub.get_message(timeout=0.5)
    while msg:
        if msg["type"] == "message":
            received.append(msg["data"])
        msg = pubsub.get_message(timeout=0.5)
    pubsub.unsubscribe("sse:job-cancel-1")

    assert received == ["first "]  # no [DONE], no [ERROR] after cancellation
    assert job_registry.get("job-cancel-1") is None