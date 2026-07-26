import httpx

from app.config import settings


class EmailSendError(Exception):
    """Raised on any provider failure -- caller is responsible for still
    logging the attempt to notification_log with status='failed'."""


async def send_email(to: str, subject: str, body_text: str) -> None:
    """Resend's sandbox API (https://resend.com/docs/send-with-python) --
    free tier, no cost, no domain verification needed when sending from
    onboarding@resend.dev. Raises EmailSendError on any non-2xx response
    or network failure."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.email_provider_base_url}/emails",
                headers={"Authorization": f"Bearer {settings.email_provider_api_key}"},
                json={
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