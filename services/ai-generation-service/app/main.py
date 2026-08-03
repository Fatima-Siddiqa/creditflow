from fastapi import FastAPI, HTTPException, status, Request

from app.api.generation import router as generation_router
from app.db import engine
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="CreditFlow AI Generation Service")

@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": "http_error", "message": str(exc.detail), "details": {}}})

app.include_router(generation_router, prefix="/ai", tags=["Generation"])

# No lifespan/consumer_task: per spec §8 Service 7's event contract
# ("Consumes: none"), this service is a publisher only, so there's no
# RabbitMQ consumer to start on startup (contrast with usage-service's
# app/main.py, which does need one).


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