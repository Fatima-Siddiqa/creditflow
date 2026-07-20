import asyncio
import logging

from app.job_registry import discard as discard_job
from app.openrouter_client import OpenRouterError, stream_chat_completion
from app.sse_publisher import publish_done, publish_error, publish_token

logger = logging.getLogger(__name__)


async def run_generation_stream(job_id: str, model: str, prompt: str) -> None:
    """Background task started by POST /ai/generate right after the
    generation_jobs/prompt_history rows are committed
    (app/api/generation.py). Streams OpenRouter's response
    token-by-token onto the `sse:<job_id>` Redis channel that the
    Gateway subscribes to and forwards to the frontend's EventSource
    (api-gateway/app/api/sse.py).

    Deliberately does NOT touch Postgres, flip generation_jobs.status,
    or publish ai.generation_completed/ai.generation_failed to
    RabbitMQ -- that's PR #4 (feature/ai-service-persistence-and-events),
    which will wrap this same OpenRouter call with the persistence step.
    Until PR #4 lands, generation_jobs stays at status=running even
    after the SSE stream finishes -- querying it mid-project only tells
    you a job was accepted, not whether it completed.
    """
    try:
        async for chunk in stream_chat_completion(model=model, prompt=prompt):
            publish_token(job_id, chunk)
    except asyncio.CancelledError:
        # PR #5 (feature/ai-service-cancel-endpoint) cancels this task
        # via job_registry.get(job_id).cancel(). Per that PR's own scope
        # ("no event published"), nothing gets published here either --
        # just let the task stop. Re-raise so asyncio actually marks the
        # task cancelled instead of this except-block silently eating it.
        raise
    except OpenRouterError as exc:
        publish_error(job_id, str(exc))
    except Exception:  # pragma: no cover - defensive catch-all
        logger.exception("Unexpected error streaming generation job %s", job_id)
        publish_error(job_id, "internal_error")
    else:
        publish_done(job_id)
    finally:
        discard_job(job_id)