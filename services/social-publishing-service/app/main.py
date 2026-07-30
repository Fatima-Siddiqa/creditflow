from fastapi import FastAPI, HTTPException, status, Request
from app.api.oauth import router as oauth_router
from app.api.publish_jobs import router as publish_jobs_router
import asyncio
from contextlib import asynccontextmanager

from app.db import engine
from app.events.publish_consumer import run_consumer
from app.token_refresh import run_token_refresh_loop
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse

@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer_task = asyncio.create_task(run_consumer())
    token_refresh_task = asyncio.create_task(run_token_refresh_loop())
    yield
    consumer_task.cancel()
    token_refresh_task.cancel()
    for task in (consumer_task, token_refresh_task):
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="CreditFlow Content Service", lifespan=lifespan)

async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": "http_error", "message": str(exc.detail), "details": {}}})

app.include_router(oauth_router, prefix="/social", tags=["Social"])
app.include_router(publish_jobs_router, prefix="/social", tags=["Social"])

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