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


def _mark_failed(db: Session, job_id: str, reason: str, model_used: str | None = None) -> str | None:
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).one_or_none()
    if job is None:
        return None
    job.status = GenerationStatus.FAILED
    job.error_reason = reason[:1000]
    job.completed_at = datetime.now(timezone.utc)
    if model_used:
        job.model = model_used
    db.commit()
    return job.account_id


def _mark_completed(db: Session, job_id: str, prompt: str, response_text: str, model_used: str):
    prompt_tokens = _estimate_tokens(prompt)
    completion_tokens = _estimate_tokens(response_text)
    total_tokens = prompt_tokens + completion_tokens
    cost_cents = 0

    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).one_or_none()
    history = db.query(PromptHistory).filter(PromptHistory.job_id == job_id).one_or_none()
    account_id = job.account_id if job is not None else None

    if job is not None:
        job.status = GenerationStatus.COMPLETED
        job.model = model_used
        job.prompt_tokens = prompt_tokens
        job.completion_tokens = completion_tokens
        job.total_tokens = total_tokens
        job.cost_cents = cost_cents
        job.completed_at = datetime.now(timezone.utc)
    if history is not None:
        history.response = response_text
    db.commit()

    content_type = job.content_type if job is not None else "chat"
    return account_id, prompt_tokens, completion_tokens, total_tokens, cost_cents, content_type

async def _publish_completed_event(job_id, account_id, model, prompt_tokens, completion_tokens, total_tokens, cost_cents, content_type, response_text) -> None:
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
                "content_type": content_type,
                "response_text": response_text,
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


async def _run_generation_stream_core(db: Session, job_id: str, models: list[str], prompt: str) -> None:
    response_chunks: list[str] = []
    result: dict = {}
    try:
        async for chunk in stream_chat_completion(models=models, prompt=prompt, result=result):
            response_chunks.append(chunk)
            publish_token(job_id, chunk)
    except asyncio.CancelledError:
        _mark_cancelled(db, job_id)
        raise
    except OpenRouterError as exc:
        reason = str(exc)
        publish_error(job_id, reason)
        account_id = _mark_failed(db, job_id, reason, result.get("model"))
        await _publish_failed_event(job_id, account_id, result.get("model", models[0]), reason)
    except Exception:
        logger.exception("Unexpected error streaming generation job %s", job_id)
        publish_error(job_id, "internal_error")
        account_id = _mark_failed(db, job_id, "internal_error", result.get("model"))
        await _publish_failed_event(job_id, account_id, result.get("model", models[0]), "internal_error")
    else:
        response_text = "".join(response_chunks)
        model_used = result.get("model", models[0])
        account_id, prompt_tokens, completion_tokens, total_tokens, cost_cents, content_type = _mark_completed(
            db, job_id, prompt, response_text, model_used
        )
        publish_done(job_id)
        await _publish_completed_event(job_id, account_id, model_used, prompt_tokens, completion_tokens, total_tokens, cost_cents, content_type, response_text)


async def run_generation_stream(job_id: str, models: list[str], prompt: str) -> None:
    db = SessionLocal()
    try:
        await _run_generation_stream_core(db, job_id, models, prompt)
    finally:
        db.close()
        discard_job(job_id)