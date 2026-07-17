from fastapi import FastAPI, HTTPException, status

from app.api.proxy import router as proxy_router
from app.api.webhooks import router as webhooks_router
from app.redis_client import redis_client

app = FastAPI(title="CreditFlow API Gateway")

app.include_router(proxy_router)
app.include_router(webhooks_router)

# Routers still to land within Phase 3:
#   app.include_router(webhooks_router)  # PR #5 — webhook intake
#   app.include_router(sse_router)       # PR #6 — SSE re-stream


@app.get("/healthz")
def healthz():
    """Liveness only — no dependency checks. Per CONVENTIONS.md."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Pings Redis — the gateway's only owned state (it has no DB, and
    it's a RabbitMQ publisher only, not a consumer, so there's no broker
    connection to hold open and check here). Per CONVENTIONS.md."""
    try:
        redis_client.ping()
        return {"status": "ok"}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "not_ready", "message": "Redis unavailable.", "details": {}}},
        )