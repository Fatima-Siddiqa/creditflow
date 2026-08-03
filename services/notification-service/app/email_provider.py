import httpx

from app.config import settings


class EmailSendError(Exception):
    """Raised on any provider failure -- caller is responsible for still
    logging the attempt to notification_log with status='failed'."""


async def send_email(to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            data = {
                "from": settings.email_from_address,
                "to": [to],
                "subject": subject,
                "text": body_text,
            }
            if body_html:
                data["html"] = body_html
            response = await client.post(
                f"{settings.email_provider_base_url}/{settings.email_provider_domain}/messages",
                auth=("api", settings.email_provider_api_key),
                data=data,
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