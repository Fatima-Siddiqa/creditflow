import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from app.api.invites import router as invites_router
from app.db import engine
from app.events.identity_consumer import run_consumer


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer_task = asyncio.create_task(run_consumer())
    yield
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="CreditFlow User/Tenant Service", lifespan=lifespan)

app.include_router(accounts_router)
app.include_router(invites_router)
# No routers yet — endpoints land in PR #3 onward.


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