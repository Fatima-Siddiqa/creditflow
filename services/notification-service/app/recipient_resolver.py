"""
Recipient resolution. Most business events (invoice.paid, payment.failed,
usage.threshold_reached, post.published, post.failed) only carry
account_id -- verified against the actual payloads billing-service,
usage-service, and social-publishing-service publish (not the phase plan's
assumptions). user.registered / user.password_reset_requested carry
email directly. member.joined carries user_id but not email.
invite.created carries email directly.

For account-only events, this resolves: account_id -> owner user_id (via
user-service's internal endpoint) -> email (via auth-service's internal
endpoint). Both endpoints were added in this phase specifically to close
this gap -- see docs/ARCHITECTURE.md "Internal cross-service calls".
"""
import httpx

from app.config import settings


class RecipientResolutionError(Exception):
    pass


async def _get(url: str) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(url, headers={"X-Internal-Secret": settings.internal_service_secret})
    response.raise_for_status()
    return response.json()


async def resolve_email_for_user(user_id: str) -> str:
    try:
        data = await _get(f"{settings.auth_service_url}/auth/internal/users/{user_id}")
    except httpx.HTTPError as exc:
        raise RecipientResolutionError(f"could not resolve email for user {user_id}: {exc}") from exc
    return data["email"]


async def resolve_email_for_account_owner(account_id: str) -> str:
    try:
        owner = await _get(f"{settings.user_service_url}/accounts/internal/{account_id}/owner")
    except httpx.HTTPError as exc:
        raise RecipientResolutionError(f"could not resolve owner for account {account_id}: {exc}") from exc
    return await resolve_email_for_user(owner["user_id"])