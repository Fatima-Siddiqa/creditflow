from app.redis_client import sse_redis_client

# Must match api-gateway/app/api/sse.py's DONE_SENTINEL/ERROR_PREFIX
# exactly -- that's the contract this whole PR exists to satisfy. If
# these ever drift from the Gateway's copy, tokens will still relay
# fine but the frontend's EventSource will never see a `done`/`error`
# event and the connection will just hang until the client gives up.
DONE_SENTINEL = "[DONE]"
ERROR_PREFIX = "[ERROR] "

_CHANNEL_PREFIX = "sse:"


def _channel(job_id: str) -> str:
    return f"{_CHANNEL_PREFIX}{job_id}"


def publish_token(job_id: str, text: str) -> None:
    """Raw token chunk, no JSON wrapping -- the Gateway forwards this
    verbatim as an SSE `token` event body."""
    sse_redis_client.publish(_channel(job_id), text)


def publish_done(job_id: str) -> None:
    sse_redis_client.publish(_channel(job_id), DONE_SENTINEL)


def publish_error(job_id: str, reason: str) -> None:
    sse_redis_client.publish(_channel(job_id), f"{ERROR_PREFIX}{reason}")