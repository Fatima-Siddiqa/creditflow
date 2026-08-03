import asyncio
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app import job_registry
from app.config import settings
from app.db import get_db
from app.dependencies import get_current_payload
from app.generation_worker import run_generation_stream
from app.models.generation import GenerationJob, GenerationStatus, PromptHistory
from app.schemas.generation import CancelResponse, GenerateRequest, GenerateResponse
from app.usage_client import check_quota

router = APIRouter()


def _error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message, "details": {}}}


@router.post("/generate", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate(
    body: GenerateRequest,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
    authorization: str | None = Header(default=None),
):
    account_id = payload["account_id"]
    models = settings.fallback_models

    quota = await check_quota(authorization)
    if not quota.get("allowed", False):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_error("quota_exceeded", "Monthly token quota exhausted for this account."),
        )

    job_id = str(uuid.uuid4())
    db.add(GenerationJob(
        id=job_id,
        account_id=account_id,
        created_by_user_id=payload["sub"],
        model=models[0],  # placeholder until the worker learns which one actually won; _mark_completed/_mark_failed overwrite this
        status=GenerationStatus.RUNNING,
        content_type=body.content_type,
    ))
    db.add(PromptHistory(
        id=str(uuid.uuid4()),
        job_id=job_id,
        account_id=account_id,
        prompt=body.prompt,
    ))
    db.commit()

    task = asyncio.create_task(run_generation_stream(job_id=job_id, models=models, prompt=body.prompt))
    job_registry.register(job_id, task)

    return GenerateResponse(job_id=job_id, status=GenerationStatus.RUNNING, model=models[0])

@router.post("/generate/{job_id}/cancel", response_model=CancelResponse, status_code=status.HTTP_202_ACCEPTED)
def cancel(
    job_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    """Spec §8 Service 7: 'Support cancellation of an in-flight stream
    (job_id-based).' Two independent checks have to both pass before we
    touch the task:

    1. The generation_jobs row must exist, belong to the caller's own
       account, and still be RUNNING -- a DB-level check, so it's
       authoritative even across a process restart (unlike #2 below).
       A job that isn't found OR isn't owned by this account gets the
       SAME 404 either way, so this endpoint can't be used to probe
       which job_ids exist on other accounts.
    2. job_registry must actually hold a live, not-yet-finished
       asyncio.Task for this job_id -- the in-memory registry
       (app/job_registry.py) only reflects tasks THIS process is running.
       A row stuck at RUNNING with no matching registry entry (this
       process restarted after the job started, or the worker's own
       `finally` already discarded it moments ago in a race) is a real,
       distinct failure mode from #1 and gets its own check rather than
       silently no-op'ing.

    Deliberately does NOT await the task or flip generation_jobs.status
    itself -- that's still entirely the worker's job (PR #4's
    asyncio.CancelledError handler in app/generation_worker.py), so
    there's exactly one code path that ever writes CANCELLED to the DB
    or decides what does/doesn't get published on cancellation.
    """
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).one_or_none()
    if job is None or job.account_id != payload["account_id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error("job_not_found", "No such generation job for this account."),
        )

    if job.status != GenerationStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_error("job_not_running", f"Job is '{job.status.value}', not running."),
        )

    task = job_registry.get(job_id)
    if task is None or task.done():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_error("job_not_running", "Job is not currently running in this process."),
        )

    task.cancel()
    return CancelResponse(job_id=job_id, status="cancelling")