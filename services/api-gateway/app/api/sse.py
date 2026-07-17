from fastapi import APIRouter, Request
from starlette.responses import StreamingResponse

import redis.asyncio as redis_asyncio
from app.config import settings
from app.dependencies import verify_access_token

router = APIRouter(prefix="/api/ai")

# ---- Contract with AI Generation Service (Phase 8, not yet built) ----
# Phase 8 PUBLISHes to Redis pub/sub channel `sse:<job_id>` (confirmed —
# see 09_PHASE8_ai_generation_service.md). What ISN'T yet specified there
# is the message format, so this defines it now, mirroring the
# OpenAI/OpenRouter SSE convention Phase 8 is already wrapping rather
# than inventing something unrelated:
#   - a normal token chunk: published as raw plain text, no JSON wrapping
#   - stream finished successfully: publish the literal string "[DONE]"
#   - stream failed: publish "[ERROR] <reason>"
# NOT yet confirmed against a real Phase 8 implementation. Update this
# comment (and the code below) if Phase 8 ends up doing something else.
DONE_SENTINEL = "[DONE]"
ERROR_PREFIX = "[ERROR] "


def _format_sse(event: str, data: str) -> str:
    """Per the SSE spec, a `data:` field can't contain a raw newline —
    each line of a multi-line payload needs its own `data:` prefix."""
    data_block = "\n".join(f"data: {line}" for line in data.split("\n"))
    return f"event: {event}\n{data_block}\n\n"


def _authenticate_sse_request(request: Request) -> dict:
    """SSE has an auth wrinkle a normal proxied request doesn't: the
    browser-native EventSource API cannot set custom headers, so a real
    frontend may not be able to send Authorization: Bearer <token> here.
    Supports BOTH:
      - Authorization header (works for curl/testing now, and for any
        frontend approach that streams via fetch() instead of native
        EventSource)
      - ?token=<access_token> query param (works for native EventSource)
    Query-param tokens have a real tradeoff — they can land in server
    access logs or browser history — flagged here rather than silently
    decided; revisit once Phase 15's actual frontend approach is chosen."""
    auth_header = request.headers.get("authorization")
    if not auth_header:
        token = request.query_params.get("token")
        auth_header = f"Bearer {token}" if token else None
    return verify_access_token(auth_header)


@router.get("/stream/{job_id}")
async def stream_ai_generation(job_id: str, request: Request):
    _authenticate_sse_request(request)  # raises 401 via verify_access_token if invalid

    async def event_generator():
        redis_conn = redis_asyncio.Redis.from_url(settings.redis_url)
        pubsub = redis_conn.pubsub()
        channel = f"sse:{job_id}"
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                if await request.is_disconnected():
                    break

                chunk = message["data"]
                if isinstance(chunk, bytes):
                    chunk = chunk.decode()

                if chunk == DONE_SENTINEL:
                    yield _format_sse("done", "")
                    break
                if chunk.startswith(ERROR_PREFIX):
                    yield _format_sse("error", chunk[len(ERROR_PREFIX):])
                    break

                yield _format_sse("token", chunk)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()  # NOT .close() — deprecated in redis-py 5.0.1+
            await redis_conn.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )