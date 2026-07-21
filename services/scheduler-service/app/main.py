from fastapi import FastAPI, HTTPException, status

from app.api.scheduled_post import router as scheduled_post_router
from app.db import engine

app = FastAPI(title="CreditFlow Scheduler Service")
app.include_router(scheduled_post_router, prefix="/scheduler", tags=["Scheduler"])


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
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail={"error": {"code": "not_ready", "message": "Database unavailable.", "details": {}}})
