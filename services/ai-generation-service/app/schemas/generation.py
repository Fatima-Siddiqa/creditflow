from typing import Optional

from pydantic import BaseModel

from app.models.generation import GenerationStatus


class GenerateRequest(BaseModel):
    prompt: str
    model: Optional[str] = None  # falls back to settings.default_model


class GenerateResponse(BaseModel):
    job_id: str
    status: GenerationStatus
    model: str


class CancelResponse(BaseModel):
    job_id: str
    # Deliberately a plain str, not GenerationStatus -- "cancelling" isn't
    # one of that enum's values. The row is still RUNNING at the instant
    # this response is built; the actual RUNNING -> CANCELLED transition
    # happens moments later inside the worker's asyncio.CancelledError
    # handler (app/generation_worker.py's _run_generation_stream_core,
    # PR #4), which this endpoint doesn't wait on.
    status: str