import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse
from app.api.accounts import router as accounts_router
from app.api.invites import router as invites_router
from app.db import engine
from app.events.identity_consumer import run_consumer as run_identity_consumer
from app.events.billing_consumer import run_consumer as run_billing_consumer


@asynccontextmanager
async def lifespan(app: FastAPI):
    identity_task = asyncio.create_task(run_identity_consumer())
    billing_task = asyncio.create_task(run_billing_consumer())
    yield
    for task in (identity_task, billing_task):
        task.cancel()
    for task in (identity_task, billing_task):
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="CreditFlow User/Tenant Service", lifespan=lifespan)

@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": "http_error", "message": str(exc.detail), "details": {}}})

app.include_router(accounts_router)
app.include_router(invites_router)


@app.get("/healthz")
def healthz():
    """Liveness only — no dependency checks. Per CONVENTIONS.md."""
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