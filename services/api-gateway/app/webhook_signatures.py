import hashlib
import hmac

import stripe
from fastapi import HTTPException, status


def _bad_signature(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error": {"code": code, "message": message, "details": {}}},
    )


def verify_stripe_signature(payload: bytes, sig_header: str | None, secret: str) -> dict:
    """Real, well-defined: uses Stripe's own SDK, which implements their
    documented HMAC-SHA256-plus-timestamp scheme (and its replay-window
    tolerance) for us. Returns the parsed event as a plain dict."""
    if not sig_header:
        raise _bad_signature("missing_signature", "Stripe-Signature header is required.")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except (stripe.error.SignatureVerificationError, ValueError):
        raise _bad_signature("invalid_signature", "Stripe webhook signature verification failed.")
    # StripeObject subclasses dict, so this is a real, non-deprecated
    # conversion (the now-deprecated .to_dict() was just `dict(self)`).
    return dict(event)


def verify_generic_hmac_signature(payload: bytes, sig_header: str | None, secret: str, source: str) -> None:
    """PLACEHOLDER scheme for LinkedIn/OpenRouter — see
    docs/EVENT_CONTRACTS.md's "Webhook relay events" section for why.
    Generic HMAC-SHA256-over-raw-body-with-shared-secret, since neither
    product has a confirmed real signing scheme for what this project
    integrates with. Replace with the actual documented scheme once the
    mentor confirms one exists (or remove the endpoint if one doesn't)."""
    if not sig_header:
        raise _bad_signature("missing_signature", f"{source} webhook signature header is required.")
    if not secret:
        raise _bad_signature(
            "webhook_not_configured", f"{source} webhook secret is not configured on this gateway."
        )
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig_header):
        raise _bad_signature("invalid_signature", f"{source} webhook signature verification failed.")