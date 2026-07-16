import httpx
from app.rate_limiter import enforce_account_rate_limit, enforce_ip_rate_limit
from fastapi import APIRouter, HTTPException, Request, Response, status

from app.dependencies import verify_access_token
from app.public_routes import is_public_route
from app.routing import resolve_service_base_url

router = APIRouter()

# Headers that must never be blindly forwarded in either direction — they
# describe THIS hop's framing, not the payload, and forwarding them stale
# causes mismatched-length / connection-reuse bugs.
_HOP_BY_HOP_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "date", "server"}

async def _forward(method: str, url: str, params, content: bytes, headers: dict) -> httpx.Response:
    """Isolated on purpose: the only place that talks to httpx directly,
    so tests can monkeypatch this one function instead of mocking httpx's
    internals."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        return await client.request(method, url, params=params, content=content, headers=headers)


@router.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(path: str, request: Request):
    prefix = path.split("/", 1)[0]
    base_url = resolve_service_base_url(prefix)

    if base_url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "route_not_found",
                    "message": f"No service registered for '/{prefix}'.",
                    "details": {},
                }
            },
        )

    # path already excludes the leading "/api/" (FastAPI's {path:path}
    # captures everything after it) — so this reconstructs exactly the
    # downstream service's own route, e.g. "auth/login" -> "/auth/login",
    # matching auth-service's router prefix.
    target_url = f"{base_url}/{path}"

    client_ip = request.client.host if request.client else "unknown"
    enforce_ip_rate_limit(client_ip)

    if not is_public_route(request.method, path):
        payload = verify_access_token(request.headers.get("authorization"))
        enforce_account_rate_limit(payload["account_id"])
        
    body = await request.body()
    forward_headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP_HEADERS}

    try:
        downstream_resp = await _forward(
            request.method, target_url, request.query_params, body, forward_headers
        )
    except httpx.ConnectError:
        # Expected and graceful for any service whose phase hasn't landed
        # yet — per Phase 3 spec, this is not a bug to fix, it's the
        # documented behavior until that service exists.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "service_unavailable",
                    "message": f"'{prefix}' service is not reachable.",
                    "details": {},
                }
            },
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "error": {
                    "code": "upstream_timeout",
                    "message": f"'{prefix}' service did not respond in time.",
                    "details": {},
                }
            },
        )

    response_headers = {
        k: v for k, v in downstream_resp.headers.items() if k.lower() not in _HOP_BY_HOP_HEADERS
    }
    return Response(
        content=downstream_resp.content,
        status_code=downstream_resp.status_code,
        headers=response_headers,
        media_type=downstream_resp.headers.get("content-type"),
    )