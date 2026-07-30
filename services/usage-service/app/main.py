import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status, Request

from app.api.usage import router as usage_router
from app.db import engine
from app.events.ai_consumer import run_consumer
from app.reconciliation import run_reconciliation_loop
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse

@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer_task = asyncio.create_task(run_consumer())
    reconciliation_task = asyncio.create_task(run_reconciliation_loop())
    yield
    for task in (consumer_task, reconciliation_task):
        task.cancel()
    for task in (consumer_task, reconciliation_task):
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="CreditFlow Usage & Metering Service", lifespan=lifespan)

@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": "http_error", "message": str(exc.detail), "details": {}}})

app.include_router(usage_router, prefix="/usage", tags=["Usage"])


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
