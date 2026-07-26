import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text

from app.api.admin import router as admin_router
from app.db import SessionLocal
from app.events.consumer import run_consumer


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(run_consumer())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="CreditFlow Admin Service", lifespan=lifespan)
app.include_router(admin_router)


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
        raise HTTPException(status_code=503, detail={"error": {"code": "not_ready", "message": "Database unavailable.", "details": {}}})
    finally:
        db.close()