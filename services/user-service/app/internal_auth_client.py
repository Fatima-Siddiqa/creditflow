import uuid

import httpx

from app.config import settings


async def issue_scoped_token(user_id: uuid.UUID, account_id: uuid.UUID, role: str) -> dict:
    """Calls auth-service's internal, service-to-service-only endpoint to
    mint an account-scoped access token — see docs/ARCHITECTURE.md
    'Internal cross-service calls'. auth-service trusts THIS call to mean
    membership was already verified; it does not re-check it itself.
    Raises httpx.HTTPError on any failure — callers turn that into a
    clean 502, not a raw exception leaking to the client."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(
            f"{settings.auth_service_url}/auth/issue-scoped-token",
            json={"user_id": str(user_id), "account_id": str(account_id), "role": role},
            headers={"X-Internal-Secret": settings.internal_service_secret},
        )
    response.raise_for_status()
    return response.json()