from fastapi import FastAPI, HTTPException, status

from app.db import engine

app = FastAPI(title="CreditFlow Scheduler Service")
# No router yet -- calendar/schedule endpoints land in PR #2
# (feature/scheduler-service-calendar-api).


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