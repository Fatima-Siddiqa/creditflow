import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.events.publisher import publish_event
from app.job_registry import discard as discard_job
from app.models.generation import GenerationJob, GenerationStatus, PromptHistory
from app.openrouter_client import OpenRouterError, stream_chat_completion
from app.sse_publisher import publish_done, publish_error, publish_token

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """~4 chars/token, a common rough heuristic for English text.

    PR #3's stream_chat_completion(model, prompt) doesn't request
    OpenRouter's usage-accounting extension (`usage: {include: true}`)
    and doesn't surface it even for models that return it unprompted --
    so there's no real token count available here to persist. This is a
    documented approximation for generation_jobs.{prompt,completion,
    total}_tokens and for the `tokens_used` figure Usage Service's
    quota ledger records off the ai.generation_completed event -- NOT a
    billing-accurate count.

    Swapping in real OpenRouter usage accounting is a natural follow-up
    PR, but it touches app/openrouter_client.py's signature (and, in
    turn, every test that monkeypatches it -- see tests/conftest.py's
    mock_openrouter_stream/mock_openrouter_error). Deliberately kept out
    of this PR to stay within "wrap the existing stream with
    persistence", per PR #3's own docstring.
    """
    return max(1, len(text) // 4)


def _mark_cancelled(db: Session, job_id: str) -> None:
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).one_or_none()
    if job is None:
        return
    job.status = GenerationStatus.CANCELLED
    job.completed_at = datetime.now(timezone.utc)
    db.commit()


def _mark_failed(db: Session, job_id: str, reason: str) -> str | None:
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).one_or_none()
    if job is None:
        return None
    job.status = GenerationStatus.FAILED
    job.error_reason = reason[:1000]
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    return job.account_id


def _mark_completed(db: Session, job_id: str, prompt: str, response_text: str):
    """Returns (account_id, prompt_tokens, completion_tokens,
    total_tokens, cost_cents) for the caller to build the
    ai.generation_completed payload from -- account_id is None if the
    job row can't be found (defensive; shouldn't happen outside tests
    that call the worker directly without going through POST /generate)."""
    prompt_tokens = _estimate_tokens(prompt)
    completion_tokens = _estimate_tokens(response_text)
    total_tokens = prompt_tokens + completion_tokens
    cost_cents = 0  # see _estimate_tokens docstring -- no real OpenRouter cost data available yet

    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).one_or_none()
    history = db.query(PromptHistory).filter(PromptHistory.job_id == job_id).one_or_none()
    account_id = job.account_id if job is not None else None

    if job is not None:
        job.status = GenerationStatus.COMPLETED
        job.prompt_tokens = prompt_tokens
        job.completion_tokens = completion_tokens
        job.total_tokens = total_tokens
        job.cost_cents = cost_cents
        job.completed_at = datetime.now(timezone.utc)
    if history is not None:
        history.response = response_text
    db.commit()

    return account_id, prompt_tokens, completion_tokens, total_tokens, cost_cents


async def _publish_completed_event(job_id, account_id, model, prompt_tokens, completion_tokens, total_tokens, cost_cents) -> None:
    try:
        await publish_event(
            "ai.generation_completed",
            {
                "job_id": job_id,
                "account_id": account_id,
                "model": model,
                # tokens_used is the REQUIRED key name -- see
                # app/events/publisher.py's docstring on why this can't
                # be renamed to total_tokens without breaking
                # usage-service's already-live consumer.
                "tokens_used": total_tokens,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost_cents": cost_cents,
            },
            account_id=account_id,
        )
    except Exception:
        logger.exception("job %s completed but failed to publish ai.generation_completed", job_id)


async def _publish_failed_event(job_id, account_id, model, reason) -> None:
    try:
        await publish_event(
            "ai.generation_failed",
            {"job_id": job_id, "account_id": account_id, "model": model, "reason": reason},
            account_id=account_id,
        )
    except Exception:
        logger.exception("job %s failed but failed to publish ai.generation_failed", job_id)


async def _run_generation_stream_core(db: Session, job_id: str, model: str, prompt: str) -> None:
    """All of run_generation_stream's actual logic, against an already-
    open, INJECTED db Session -- does not open or close it (though it
    does call db.commit()/db.rollback() at the right points via the
    _mark_* helpers above). Split out from run_generation_stream()
    below purely for testability: tests can call this directly with the
    same rollback-wrapped db_session fixture used to create the job row
    in the first place, so both live in the same Postgres transaction
    and can see each other's writes -- calling the real
    run_generation_stream() from a test would open a genuinely separate
    connection via SessionLocal() that can't see a row the test's own
    transaction hasn't actually committed to the database yet.
    """
    response_chunks: list[str] = []
    try:
        async for chunk in stream_chat_completion(model=model, prompt=prompt):
            response_chunks.append(chunk)
            publish_token(job_id, chunk)
    except asyncio.CancelledError:
        # PR #5's contract is silence on cancel: no SSE [DONE]/[ERROR],
        # no ai_events publish. We DO still record the cancellation in
        # Postgres (status=CANCELLED) so a GET on the job afterward
        # reports the truth instead of leaving it stuck at RUNNING
        # forever -- that's new in this PR, everything else about
        # cancellation's silence is unchanged from PR #5's scope.
        _mark_cancelled(db, job_id)
        raise
    except OpenRouterError as exc:
        reason = str(exc)
        publish_error(job_id, reason)
        account_id = _mark_failed(db, job_id, reason)
        await _publish_failed_event(job_id, account_id, model, reason)
    except Exception:
        logger.exception("Unexpected error streaming generation job %s", job_id)
        publish_error(job_id, "internal_error")
        account_id = _mark_failed(db, job_id, "internal_error")
        await _publish_failed_event(job_id, account_id, model, "internal_error")
    else:
        response_text = "".join(response_chunks)
        account_id, prompt_tokens, completion_tokens, total_tokens, cost_cents = _mark_completed(
            db, job_id, prompt, response_text
        )
        publish_done(job_id)
        await _publish_completed_event(job_id, account_id, model, prompt_tokens, completion_tokens, total_tokens, cost_cents)


async def run_generation_stream(job_id: str, model: str, prompt: str) -> None:
    """Background task started by POST /ai/generate right after the
    generation_jobs/prompt_history rows are committed
    (app/api/generation.py). Streams OpenRouter's response token-by-
    token onto the `sse:<job_id>` Redis channel the Gateway subscribes
    to and forwards to the frontend's EventSource
    (api-gateway/app/api/sse.py), and -- as of this PR -- once the
    stream ends, persists the final response + token counts to
    Postgres and publishes ai.generation_completed / ai.generation_failed
    to RabbitMQ. Cancellation (PR #5) still publishes nothing to
    ai_events, per that PR's own contract.

    Owns its own DB session open/close -- same pattern as
    usage-service's app/events/ai_consumer.py's _handle_event -- since
    it outlives the FastAPI request that spawned it and can't reuse a
    request-scoped session. All the actual logic lives in
    _run_generation_stream_core() above; this function is just session
    + registry lifecycle around it.
    """
    db = SessionLocal()
    try:
        await _run_generation_stream_core(db, job_id, model, prompt)
    finally:
        db.close()
        discard_job(job_id)