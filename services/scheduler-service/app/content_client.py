import httpx

from app.config import settings


async def get_content(content_id: str, authorization_header: str) -> dict | None:
    """Forwards the caller's JWT -- content-service scopes GET
    /content/{id} to the token's own account_id and 404s otherwise (see
    content-service/app/api/content.py's _get_owned_content), so this
    naturally rejects cross-account content_ids too. Returns None on 404,
    raises httpx.HTTPError on any other failure."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            f"{settings.content_service_url}/content/{content_id}",
            headers={"Authorization": authorization_header},
        )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()
