import httpx
from fastapi import HTTPException, status

from app.config import settings

_HEADERS = {"X-Internal-Secret": settings.internal_service_secret}


async def _get(url: str, params: dict | None = None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params=params, headers=_HEADERS)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "upstream_unreachable", "message": str(exc), "details": {}}},
        )


async def get_account_profile(account_id: str) -> dict:
    return await _get(f"{settings.user_service_url}/accounts/internal/{account_id}")


async def list_accounts(search: str | None, limit: int, offset: int) -> dict:
    return await _get(f"{settings.user_service_url}/accounts/internal", {"search": search, "limit": limit, "offset": offset})


async def get_credit_balance(account_id: str) -> dict:
    return await _get(f"{settings.credits_service_url}/credits/balance", {"account_id": account_id})


async def get_usage_summary(account_id: str) -> dict:
    return await _get(f"{settings.usage_service_url}/usage/summary", {"account_id": account_id})