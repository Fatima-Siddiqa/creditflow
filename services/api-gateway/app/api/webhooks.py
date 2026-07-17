import hashlib
import json

from fastapi import APIRouter, Request, status

from app.config import settings
from app.events.publisher import publish_event
from app.webhook_dedup import is_duplicate_event
from app.webhook_signatures import verify_generic_hmac_signature, verify_stripe_signature

router = APIRouter(prefix="/webhooks")


def _extract_event_id(payload: bytes, body: dict) -> str:
    """Prefers an explicit id/event_id field; falls back to a content
    hash when neither is present. The fallback exists specifically for
    the LinkedIn/OpenRouter placeholders, whose real payload shape isn't
    confirmed — see docs/EVENT_CONTRACTS.md."""
    return body.get("id") or body.get("event_id") or hashlib.sha256(payload).hexdigest()


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    event = verify_stripe_signature(payload, sig_header, settings.stripe_webhook_secret)

    if is_duplicate_event(event["id"]):
        # Stripe redelivers on any non-2xx/timeout response — returning
        # 200 here (not an error) is what tells Stripe to stop retrying.
        return {"status": "duplicate_ignored"}

    await publish_event(
        exchange_name="billing_events",
        event_type="billing.webhook_received",
        payload={"source": "stripe", "raw_event": event},
    )
    return {"status": "accepted"}


@router.post("/linkedin", status_code=status.HTTP_200_OK)
async def linkedin_webhook(request: Request):
    """PLACEHOLDER pending mentor confirmation — see
    docs/EVENT_CONTRACTS.md's "Webhook relay events" section. LinkedIn's
    Sign-In/Share products don't have a confirmed inbound webhook for
    this project's scope; this exists to satisfy spec §8 Service 1's
    literal requirement."""
    payload = await request.body()
    sig_header = request.headers.get("x-linkedin-signature")
    verify_generic_hmac_signature(payload, sig_header, settings.linkedin_webhook_secret, "LinkedIn")

    body = json.loads(payload) if payload else {}
    event_id = _extract_event_id(payload, body)

    if is_duplicate_event(event_id):
        return {"status": "duplicate_ignored"}

    await publish_event(
        exchange_name="social_events",
        event_type="social.webhook_received",
        payload={"source": "linkedin", "raw_event": body},
    )
    return {"status": "accepted"}


@router.post("/openrouter", status_code=status.HTTP_200_OK)
async def openrouter_webhook(request: Request):
    """PLACEHOLDER pending mentor confirmation — see
    docs/EVENT_CONTRACTS.md's "Webhook relay events" section.
    OpenRouter's completions API is synchronous/streaming, not
    webhook-based; this endpoint exists only because spec §8 Service 1
    lists it with no hedge."""
    payload = await request.body()
    sig_header = request.headers.get("x-openrouter-signature")
    verify_generic_hmac_signature(payload, sig_header, settings.openrouter_webhook_secret, "OpenRouter")

    body = json.loads(payload) if payload else {}
    event_id = _extract_event_id(payload, body)

    if is_duplicate_event(event_id):
        return {"status": "duplicate_ignored"}

    await publish_event(
        exchange_name="ai_events",
        event_type="ai.webhook_received",
        payload={"source": "openrouter", "raw_event": body},
    )
    return {"status": "accepted"}