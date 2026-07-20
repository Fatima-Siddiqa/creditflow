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
from app.schemas.generation import GenerateRequest, GenerateResponse
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
    """Creates the job row, starts the background OpenRouter stream, and
    returns job_id immediately. Per spec §4's "streaming AI text output
    (SSE, token-by-token)" requirement, the frontend calls this then
    immediately opens GET /api/ai/stream/{job_id} on the Gateway -- there
    is no window where it's waiting on a synchronous generation call to
    finish before it can start listening.

    asyncio.create_task (not FastAPI's BackgroundTasks) is deliberate:
    the stream must keep running independent of this request/response's
    own lifecycle, including if the client disconnects immediately after
    getting job_id back."""
    account_id = payload["account_id"]
    model = body.model or settings.default_model
    if model not in settings.allowed_models:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error("invalid_model", f"'{model}' is not in the allowed model list."),
        )

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
        model=model,
        status=GenerationStatus.RUNNING,
    ))
    db.add(PromptHistory(
        id=str(uuid.uuid4()),
        job_id=job_id,
        account_id=account_id,
        prompt=body.prompt,
    ))
    db.commit()

    task = asyncio.create_task(run_generation_stream(job_id=job_id, model=model, prompt=body.prompt))
    job_registry.register(job_id, task)

    return GenerateResponse(job_id=job_id, status=GenerationStatus.RUNNING, model=model)