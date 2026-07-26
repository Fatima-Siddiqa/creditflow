import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.email_provider import send_email, send_slack_alert, EmailSendError
from app.models import NotificationLog
from app.recipient_resolver import RecipientResolutionError
from app.templates import RESOLVERS

logger = logging.getLogger("dispatcher")


def _mark_processed_or_skip(db: Session, event_id: str) -> bool:
    inserted = db.execute(
        text(
            "INSERT INTO notification.processed_events (event_id) VALUES (:event_id) "
            "ON CONFLICT DO NOTHING RETURNING event_id"
        ),
        {"event_id": event_id},
    ).fetchone()
    return inserted is not None


async def handle_event(event: dict) -> bool:
    """Returns True if a fresh (non-duplicate) event was fully processed
    (send attempted + logged), regardless of whether the send itself
    succeeded -- the caller uses this to decide whether to publish
    notification.sent."""
    event_type = event.get("event_type")
    resolver = RESOLVERS.get(event_type)
    if resolver is None:
        logger.info("no resolver registered for event_type %s, skipping", event_type)
        return False

    db = SessionLocal()
    try:
        if not _mark_processed_or_skip(db, event["event_id"]):
            logger.info("event %s already processed, skipping", event["event_id"])
            db.commit()
            return False
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    try:
        recipient, subject, body = await resolver(event["payload"])
    except RecipientResolutionError as exc:
        logger.error("recipient resolution failed for %s: %s", event_type, exc)
        _log_attempt(event_type, recipient="unknown", status="failed", error=str(exc))
        await send_slack_alert(f"notification-service: could not resolve recipient for {event_type}: {exc}")
        return True

    try:
        await send_email(recipient, subject, body)
    except EmailSendError as exc:
        logger.error("email send failed for %s to %s: %s", event_type, recipient, exc)
        _log_attempt(event_type, recipient, status="failed", error=str(exc))
        await send_slack_alert(f"notification-service: email send failed for {event_type} to {recipient}: {exc}")
        return True

    _log_attempt(event_type, recipient, status="sent", error=None)
    return True


def _log_attempt(event_type: str, recipient: str, status: str, error: str | None) -> None:
    db = SessionLocal()
    try:
        db.add(NotificationLog(type=event_type, recipient=recipient, status=status, error=error))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()