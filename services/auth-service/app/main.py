from fastapi import FastAPI, HTTPException, status

from app.api.auth import router as auth_router
from app.db import engine

app = FastAPI(title="CreditFlow Auth Service")

app.include_router(auth_router)


@app.get("/healthz")
def healthz():
    """Liveness only — no dependency checks. Per CONVENTIONS.md."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Actually pings Postgres. Per CONVENTIONS.md — used before compose
    considers this service ready to receive traffic."""
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return {"status": "ok"}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "not_ready", "message": "Database unavailable.", "details": {}}},
        )