import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status

from app.api.jobs import router as jobs_router
from app.db import ping
from app.events.request_consumer import run_consumer
from app.recurring_loop import run_recurring_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer_task = asyncio.create_task(run_consumer())
    recurring_task = asyncio.create_task(run_recurring_loop())
    yield
    consumer_task.cancel()
    recurring_task.cancel()
    for task in (consumer_task, recurring_task):
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="CreditFlow Scraper Service", lifespan=lifespan)

app.include_router(jobs_router, prefix="/scraper", tags=["Scraper"])


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    try:
        ping()
        return {"status": "ok"}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "not_ready", "message": "MongoDB unavailable.", "details": {}}},
        )