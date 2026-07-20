import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.dependencies import get_current_payload
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
    """Creates the job row and returns job_id immediately -- does NOT call
    OpenRouter or start the background stream yet (that's PR #3,
    feature/ai-service-openrouter-streaming). This lets the frontend open
    its SSE connection to GET /api/ai/stream/{job_id} on the gateway
    right after this call returns, per spec §4's 'streaming AI text
    output (SSE, token-by-token)' requirement -- there's no window where
    the frontend is waiting on a synchronous generation call to finish
    before it can start listening."""
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

    return GenerateResponse(job_id=job_id, status=GenerationStatus.RUNNING, model=model)