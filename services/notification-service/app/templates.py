"""One resolver function per consumed event type. Each returns
(recipient_email, subject, body_text, body_html)."""
from app.recipient_resolver import resolve_email_for_user, resolve_email_for_account_owner
from app.config import settings


def _button_html(intro: str, link: str, label: str) -> str:
    return (
        f"<p>{intro}</p>"
        f'<p><a href="{link}" style="display:inline-block;padding:10px 20px;'
        f'background:#4f46e5;color:#fff;text-decoration:none;border-radius:6px;">{label}</a></p>'
        f'<p style="color:#666;font-size:12px;">If the button doesn\'t work, copy this link: {link}</p>'
    )


async def user_registered(payload: dict) -> tuple[str, str, str, str]:
    token = payload["verification_token"]
    link = f"{settings.frontend_origin}/verify-email?token={token}"
    text = f"Welcome to CreditFlow! Click the link to verify your email: {link}"
    html = _button_html("Welcome to CreditFlow! Verify your email to get started.", link, "Verify email")
    return payload["email"], "Verify your CreditFlow email", text, html


async def user_password_reset_requested(payload: dict) -> tuple[str, str, str, str]:
    otp = payload["otp"]
    text = f"Your CreditFlow password reset code is: {otp}. It expires in 15 minutes."
    html = f"<p>Your CreditFlow password reset code is: <strong>{otp}</strong>. It expires in 15 minutes.</p>"
    return payload["email"], "Your CreditFlow password reset code", text, html


async def invoice_paid(payload: dict) -> tuple[str, str, str, str]:
    to = await resolve_email_for_account_owner(payload["account_id"])
    amount = payload.get("amount_cents", 0) / 100
    text = f"Your payment of ${amount:.2f} was received. Thanks for using CreditFlow!"
    return to, "Payment receipt", text, f"<p>{text}</p>"


async def payment_failed(payload: dict) -> tuple[str, str, str, str]:
    to = await resolve_email_for_account_owner(payload["account_id"])
    text = "Your recent payment failed. Please update your payment method to avoid a plan downgrade."
    return to, "Payment failed", text, f"<p>{text}</p>"


async def member_joined(payload: dict) -> tuple[str, str, str, str]:
    to = await resolve_email_for_user(payload["user_id"])
    text = f"You've joined a CreditFlow team account with role: {payload.get('role', 'member')}."
    return to, "You joined a CreditFlow account", text, f"<p>{text}</p>"


async def invite_created(payload: dict) -> tuple[str, str, str, str]:
    link = f"{settings.frontend_origin}/onboarding?invite_token={payload['token']}"
    team_name = payload.get("account_name") or "a CreditFlow team account"
    text = f"You've been invited to join {team_name}. Click to accept: {link}"
    html = _button_html(f"You've been invited to join <strong>{team_name}</strong> on CreditFlow.", link, "Accept invite")
    return payload["email"], f"You're invited to join {team_name} on CreditFlow", text, html


async def post_published(payload: dict) -> tuple[str, str, str, str]:
    to = await resolve_email_for_account_owner(payload["account_id"])
    text = "Your scheduled post was published to LinkedIn successfully."
    return to, "Post published", text, f"<p>{text}</p>"


async def post_failed(payload: dict) -> tuple[str, str, str, str]:
    to = await resolve_email_for_account_owner(payload["account_id"])
    reason = payload.get("reason", "unknown error")
    text = f"Your scheduled post failed to publish: {reason}"
    return to, "Post failed to publish", text, f"<p>{text}</p>"


async def usage_threshold_reached(payload: dict) -> tuple[str, str, str, str]:
    to = await resolve_email_for_account_owner(payload["account_id"])
    threshold = payload.get("threshold")
    text = f"Your account has crossed {threshold}% of its usage quota for this period."
    return to, "Usage quota alert", text, f"<p>{text}</p>"


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