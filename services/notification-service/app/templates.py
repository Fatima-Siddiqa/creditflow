"""One resolver function per consumed event type. Each returns
(recipient_email, subject, body_text)."""
from app.recipient_resolver import resolve_email_for_user, resolve_email_for_account_owner


async def user_registered(payload: dict) -> tuple[str, str, str]:
    token = payload["verification_token"]
    body = f"Welcome to CreditFlow! Verify your email using this token: {token}"
    return payload["email"], "Verify your CreditFlow email", body


async def user_password_reset_requested(payload: dict) -> tuple[str, str, str]:
    otp = payload["otp"]
    body = f"Your CreditFlow password reset code is: {otp}. It expires in 15 minutes."
    return payload["email"], "Your CreditFlow password reset code", body


async def invoice_paid(payload: dict) -> tuple[str, str, str]:
    to = await resolve_email_for_account_owner(payload["account_id"])
    amount = payload.get("amount_cents", 0) / 100
    body = f"Your payment of ${amount:.2f} was received. Thanks for using CreditFlow!"
    return to, "Payment receipt", body


async def payment_failed(payload: dict) -> tuple[str, str, str]:
    to = await resolve_email_for_account_owner(payload["account_id"])
    body = "Your recent payment failed. Please update your payment method to avoid a plan downgrade."
    return to, "Payment failed", body


async def member_joined(payload: dict) -> tuple[str, str, str]:
    to = await resolve_email_for_user(payload["user_id"])
    body = f"You've joined a CreditFlow team account with role: {payload.get('role', 'member')}."
    return to, "You joined a CreditFlow account", body


async def invite_created(payload: dict) -> tuple[str, str, str]:
    body = "You've been invited to join a CreditFlow team account. Log in or sign up to accept."
    return payload["email"], "You're invited to CreditFlow", body


async def post_published(payload: dict) -> tuple[str, str, str]:
    to = await resolve_email_for_account_owner(payload["account_id"])
    body = "Your scheduled post was published to LinkedIn successfully."
    return to, "Post published", body


async def post_failed(payload: dict) -> tuple[str, str, str]:
    to = await resolve_email_for_account_owner(payload["account_id"])
    reason = payload.get("reason", "unknown error")
    body = f"Your scheduled post failed to publish: {reason}"
    return to, "Post failed to publish", body


async def usage_threshold_reached(payload: dict) -> tuple[str, str, str]:
    to = await resolve_email_for_account_owner(payload["account_id"])
    threshold = payload.get("threshold")
    body = f"Your account has crossed {threshold}% of its usage quota for this period."
    return to, "Usage quota alert", body


RESOLVERS = {
    "user.registered": user_registered,
    "user.password_reset_requested": user_password_reset_requested,
    "invoice.paid": invoice_paid,
    "payment.failed": payment_failed,
    "member.joined": member_joined,
    "invite.created": invite_created,
    "post.published": post_published,
    "post.failed": post_failed,
    "usage.threshold_reached": usage_threshold_reached,
}