import httpx
from fastapi import HTTPException, status

from app.config import settings


async def check_quota(authorization: str) -> dict:
    """Spec §8 Service 7: 'Accept a generation request only after a
    synchronous quota check against Usage Service.' Forwards the
    caller's OWN Authorization header rather than INTERNAL_SERVICE_SECRET
    -- usage-service's GET /usage/check deliberately only ever answers
    for the JWT's own account_id (see usage-service/app/api/usage.py's
    check_quota docstring), so there's no cross-account read to
    authorize here, just a pass-through of the same token.

    Raises HTTPException(503) if usage-service is unreachable. Per
    docs/CONVENTIONS.md, no service's test suite depends on another
    service actually running -- this function is monkeypatched in
    tests/test_generation.py rather than exercised for real there."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{settings.usage_service_url}/usage/check",
                headers={"Authorization": authorization},
            )
        response.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "usage_service_unreachable", "message": "Could not verify quota.", "details": {}}},
        )
    return response.json()