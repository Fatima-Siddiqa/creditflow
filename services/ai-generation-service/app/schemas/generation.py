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