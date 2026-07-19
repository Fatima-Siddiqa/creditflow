import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status

from app.api.billing import router as billing_router
from app.db import engine
from app.dunning import run_dunning_checker
from app.events.stripe_consumer import run_consumer
from app.outbox import run_outbox_poller


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [
        asyncio.create_task(run_consumer()),
        asyncio.create_task(run_outbox_poller()),
        asyncio.create_task(run_dunning_checker()),
    ]
    yield
    for t in tasks:
        t.cancel()
    for t in tasks:
        try:
            await t
        except asyncio.CancelledError:
            pass


app = FastAPI(title="CreditFlow Billing Service", lifespan=lifespan)
app.include_router(billing_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"error": {"code": "not_ready", "message": "Database unavailable.", "details": {}}})