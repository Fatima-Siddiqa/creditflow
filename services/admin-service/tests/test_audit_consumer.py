import uuid

from sqlalchemy import text

from app.events.consumer import EXCHANGES, _write_audit_row


def _event(event_type: str, account_id: str | None = None, event_id: str | None = None) -> dict:
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": event_type,
        "account_id": account_id,
        "payload": {"note": f"test payload for {event_type}"},
        "occurred_at": "2026-07-26T00:00:00+00:00",
    }


# One representative routing key per exchange — per PHASE_14's test
# checklist: "don't need to test all 20+ event types individually, but
# cover one per exchange to prove the binding works."
REPRESENTATIVE_EVENTS = {
    "identity_events": "user.registered",
    "account_events": "member.joined",
    "billing_events": "invoice.paid",
    "credits_events": "credits.credited",
    "usage_events": "usage.threshold_reached",
    "ai_events": "ai.generation_completed",
    "content_events": "content.created",
    "social_events": "post.published",
    "scraper_events": "scrape.completed",
    "notification_events": "notification.sent",
}


def test_representative_event_from_every_exchange_is_audited(db_session):
    assert set(REPRESENTATIVE_EVENTS) == set(EXCHANGES), "every exchange in the topology needs a covered routing key"

    for exchange_name, event_type in REPRESENTATIVE_EVENTS.items():
        event = _event(event_type, account_id=str(uuid.uuid4()))
        written = _write_audit_row(event)
        assert written is True, f"expected {exchange_name}/{event_type} to be written"

        row = db_session.execute(
            text("SELECT event_type, account_id FROM admin.audit_log WHERE event_id = :eid"),
            {"eid": event["event_id"]},
        ).fetchone()
        assert row is not None
        assert row.event_type == event_type


def test_duplicate_event_id_is_not_written_twice(db_session):
    event = _event("user.registered", event_id=str(uuid.uuid4()))

    first = _write_audit_row(event)
    second = _write_audit_row(event)

    assert first is True
    assert second is False

    count = db_session.execute(
        text("SELECT count(*) FROM admin.audit_log WHERE event_id = :eid"),
        {"eid": event["event_id"]},
    ).scalar()
    assert count == 1


def test_event_with_no_account_id_is_still_audited(db_session):
    """Some events (e.g. scrape.requested-style platform jobs) may have no
    account_id — audit_log.account_id is nullable for exactly this case."""
    event = _event("scrape.completed", account_id=None)
    assert _write_audit_row(event) is True

    row = db_session.execute(
        text("SELECT account_id FROM admin.audit_log WHERE event_id = :eid"),
        {"eid": event["event_id"]},
    ).fetchone()
    assert row.account_id is None