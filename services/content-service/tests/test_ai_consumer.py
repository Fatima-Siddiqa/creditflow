import uuid

from app.events.ai_consumer import apply_generation_completed
from app.models.content import Content


def _event(account_id="acc_123", content_type="post", response_text="generated post body", event_id=None):
    return {
        "event_id": str(event_id or uuid.uuid4()),
        "event_type": "ai.generation_completed",
        "payload": {"account_id": account_id, "content_type": content_type, "response_text": response_text},
    }


def test_post_type_creates_a_draft(db_session):
    applied = apply_generation_completed(db_session, _event())
    db_session.flush()

    assert applied is True
    rows = db_session.query(Content).filter(Content.account_id == "acc_123").all()
    assert len(rows) == 1
    assert rows[0].status.value == "draft"


def test_chat_type_creates_nothing(db_session):
    applied = apply_generation_completed(db_session, _event(content_type="chat"))
    db_session.flush()

    assert applied is False
    assert db_session.query(Content).filter(Content.account_id == "acc_123").count() == 0


def test_missing_content_type_creates_nothing(db_session):
    event = _event()
    del event["payload"]["content_type"]
    applied = apply_generation_completed(db_session, event)
    assert applied is False


def test_duplicate_event_id_is_a_noop(db_session):
    event_id = uuid.uuid4()
    event = _event(event_id=event_id)

    first = apply_generation_completed(db_session, event)
    db_session.flush()
    second = apply_generation_completed(db_session, event)

    assert first is True
    assert second is False
    assert db_session.query(Content).filter(Content.account_id == "acc_123").count() == 1