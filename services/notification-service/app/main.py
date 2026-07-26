import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text

from app.db import SessionLocal
from app.events.consumer import run_consumer


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer_task = asyncio.create_task(run_consumer())
    yield
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="CreditFlow Notification Service", lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "not_ready", "message": "Database unavailable.", "details": {}}},
        )
    finally:
        db.close()