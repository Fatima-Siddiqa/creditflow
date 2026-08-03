from fastapi import FastAPI, HTTPException, status, Request
from fastapi.staticfiles import StaticFiles
from app.api.content import router as content_router
import asyncio
import os
from contextlib import asynccontextmanager
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import engine
from app.events.ai_consumer import run_consumer as run_ai_consumer
from app.events.social_consumer import run_consumer as run_social_consumer


@asynccontextmanager
async def lifespan(app: FastAPI):
    ai_task = asyncio.create_task(run_ai_consumer())
    social_task = asyncio.create_task(run_social_consumer())
    yield
    for task in (ai_task, social_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="CreditFlow Content Service", lifespan=lifespan)
@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": "http_error", "message": str(exc.detail), "details": {}}})

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