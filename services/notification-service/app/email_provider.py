import httpx

from app.config import settings


class EmailSendError(Exception):
    """Raised on any provider failure -- caller is responsible for still
    logging the attempt to notification_log with status='failed'."""


async def send_email(to: str, subject: str, body_text: str) -> None:
    """Mailgun's sandbox API -- free tier, no cost. Sandbox domains only
    deliver to recipients added as Authorized Recipients (and who've
    clicked the activation link) until you verify your own domain.
    Raises EmailSendError on any non-2xx response or network failure."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.email_provider_base_url}/{settings.email_provider_domain}/messages",
                auth=("api", settings.email_provider_api_key),
                data={
                    "from": settings.email_from_address,
                    "to": [to],
                    "subject": subject,
                    "text": body_text,
                },
            )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise EmailSendError(str(exc)) from exc


async def send_slack_alert(message: str) -> None:
    """Optional ops visibility (spec §8 Service 12). No-ops silently if
    unconfigured."""
    if not settings.slack_webhook_url:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(settings.slack_webhook_url, json={"text": message})
    except httpx.HTTPError:
        pass