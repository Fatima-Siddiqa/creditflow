from fastapi import FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles
from app.api.content import router as content_router
import asyncio
import os
from contextlib import asynccontextmanager

from app.config import settings
from app.db import engine
from app.events.ai_consumer import run_consumer


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer_task = asyncio.create_task(run_consumer())
    yield
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="CreditFlow Content Service", lifespan=lifespan)

app.include_router(content_router, prefix="/content", tags=["Content"])

# Serves whatever upload_content_image wrote to settings.upload_dir, at
# the exact path shape stored in Content.image_url
# (f"/uploads/{content_id}/{filename}") -- this mount was missing
# entirely before, so image_url pointed at a path nothing served over
# HTTP: not the frontend, not social-publishing-service's fetch of the
# bytes for LinkedIn's Images API.
os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@app.get("/healthz")
def healthz():
    """Liveness only -- no dependency checks. Per CONVENTIONS.md."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Actually pings Postgres. Per CONVENTIONS.md."""
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return {"status": "ok"}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "not_ready", "message": "Database unavailable.", "details": {}}},
        )