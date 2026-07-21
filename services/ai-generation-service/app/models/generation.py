import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.db import Base


class GenerationStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenerationJob(Base):
    """Operational/status tracking, one row per POST /generate call. `id`
    doubles as the job_id used in the SSE channel name (sse:<job_id>,
    Redis index 3 -- see api-gateway/app/api/sse.py) and in
    POST /generate/{job_id}/cancel (PR #5). Kept separate from
    PromptHistory so a status poll doesn't have to pull the full prompt/
    response text -- mirrors usage-service's split between its Redis
    counters (fast/live) and usage_ledger (durable/full detail)."""

    __tablename__ = "generation_jobs"

    id = Column(String, primary_key=True)
    account_id = Column(String, index=True, nullable=False)
    created_by_user_id = Column(String, nullable=False)  # audit attribution, spec §6
    model = Column(String, nullable=False)
    status = Column(Enum(GenerationStatus, name="generationstatus", schema="ai"), nullable=False, default=GenerationStatus.RUNNING)

    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    cost_cents = Column(Integer, nullable=True)
    error_reason = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    content_type = Column(String, nullable=False, default="chat")

class PromptHistory(Base):
    """The actual prompt/response text, one row per job. response stays
    NULL until the stream completes (PR #4) -- a row existing here with a
    NULL response means "still running", same shape as generation_jobs.status
    == RUNNING, kept in sync by whichever code path writes completion."""

    __tablename__ = "prompt_history"

    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("generation_jobs.id"), index=True, nullable=False)
    account_id = Column(String, index=True, nullable=False)
    prompt = Column(Text, nullable=False)
    response = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())