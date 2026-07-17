import asyncio

import pytest
import redis.asyncio as redis_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app

TEST_REDIS_URL = "redis://localhost:6380/15"


async def _publish_after_delay(channel: str, messages: list[str], delay: float = 0.05):
    """Gives the SSE endpoint time to subscribe before anything is
    published — otherwise messages sent before the subscription exists
    would be silently lost, same as any real pub/sub system."""
    await asyncio.sleep(delay)
    conn = redis_asyncio.Redis.from_url(TEST_REDIS_URL)
    for msg in messages:
        await conn.publish(channel, msg)
        await asyncio.sleep(0.01)
    await conn.aclose()


@pytest.mark.asyncio
async def test_sse_stream_relays_tokens_and_closes_on_done(monkeypatch, make_token, test_redis_client):
    monkeypatch.setattr("app.config.settings.redis_url", TEST_REDIS_URL)

    token = make_token(jti="sse-jti")
    test_redis_client.setex("jti:sse-jti", 900, "1")

    job_id = "job-tokens-123"
    publish_task = asyncio.create_task(_publish_after_delay(f"sse:{job_id}", ["Hel", "lo", "[DONE]"]))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with ac.stream(
            "GET", f"/api/ai/stream/{job_id}", headers={"Authorization": f"Bearer {token}"}
        ) as resp:
            assert resp.status_code == 200
            body = ""
            async for chunk in resp.aiter_text():
                body += chunk
                if "event: done" in body:
                    break

    await publish_task
    assert "event: token\ndata: Hel" in body
    assert "event: token\ndata: lo" in body
    assert "event: done" in body


@pytest.mark.asyncio
async def test_sse_stream_relays_error_sentinel(monkeypatch, make_token, test_redis_client):
    monkeypatch.setattr("app.config.settings.redis_url", TEST_REDIS_URL)

    token = make_token(jti="sse-jti-2")
    test_redis_client.setex("jti:sse-jti-2", 900, "1")

    job_id = "job-error-456"
    publish_task = asyncio.create_task(
        _publish_after_delay(f"sse:{job_id}", ["[ERROR] OpenRouter timed out"])
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with ac.stream(
            "GET", f"/api/ai/stream/{job_id}", headers={"Authorization": f"Bearer {token}"}
        ) as resp:
            body = ""
            async for chunk in resp.aiter_text():
                body += chunk
                if "event: error" in body:
                    break

    await publish_task
    assert "event: error\ndata: OpenRouter timed out" in body


@pytest.mark.asyncio
async def test_sse_stream_requires_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/ai/stream/some-job")
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "missing_token"


@pytest.mark.asyncio
async def test_sse_stream_accepts_token_via_query_param(monkeypatch, make_token, test_redis_client):
    """Confirms the EventSource-compatible fallback actually works, not
    just the header path."""
    monkeypatch.setattr("app.config.settings.redis_url", TEST_REDIS_URL)

    token = make_token(jti="sse-jti-3")
    test_redis_client.setex("jti:sse-jti-3", 900, "1")

    job_id = "job-query-789"
    publish_task = asyncio.create_task(_publish_after_delay(f"sse:{job_id}", ["[DONE]"]))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with ac.stream("GET", f"/api/ai/stream/{job_id}?token={token}") as resp:
            assert resp.status_code == 200
            body = ""
            async for chunk in resp.aiter_text():
                body += chunk
                if "event: done" in body:
                    break

    await publish_task
    assert "event: done" in body