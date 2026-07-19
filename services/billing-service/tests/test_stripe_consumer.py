import uuid

from app.events.stripe_consumer import _handle_stripe_event
from app.models import Invoice, ProcessedEvent, Subscription


def _seed_subscription(db_session, account_id, customer_id="cus_test123"):
    sub = Subscription(account_id=account_id, stripe_customer_id=customer_id, plan_tier="free", status="active")
    db_session.add(sub)
    db_session.commit()
    return sub


def _raw_stripe_event(event_id, event_type, obj):
    """Matches the ACTUAL shape api-gateway relays — a real Stripe event
    object, not an invented wrapper."""
    return {"id": event_id, "type": event_type, "data": {"object": obj}}


def test_invoice_paid_updates_subscription_and_creates_invoice(db_session, monkeypatch):
    account_id = uuid.uuid4()
    _seed_subscription(db_session, account_id)
    monkeypatch.setattr("app.events.stripe_consumer.SessionLocal", lambda: db_session)

    raw_event = _raw_stripe_event("evt_test1", "invoice.paid", {"id": "in_test1", "customer": "cus_test123", "amount_paid": 2900})
    _handle_stripe_event(raw_event)

    sub = db_session.query(Subscription).filter(Subscription.account_id == account_id).one()
    assert sub.status == "active"

    invoice = db_session.query(Invoice).filter(Invoice.stripe_invoice_id == "in_test1").one()
    assert invoice.amount_cents == 2900
    assert invoice.status == "paid"


def test_duplicate_stripe_event_id_is_a_noop(db_session, monkeypatch):
    account_id = uuid.uuid4()
    _seed_subscription(db_session, account_id)
    monkeypatch.setattr("app.events.stripe_consumer.SessionLocal", lambda: db_session)

    raw_event = _raw_stripe_event("evt_test2", "invoice.paid", {"id": "in_test2", "customer": "cus_test123", "amount_paid": 2900})
    _handle_stripe_event(raw_event)
    _handle_stripe_event(raw_event)

    assert db_session.query(Invoice).filter(Invoice.stripe_invoice_id == "in_test2").count() == 1
    assert db_session.query(ProcessedEvent).filter(ProcessedEvent.stripe_event_id == "evt_test2").count() == 1


def test_payment_failed_sets_grace_period(db_session, monkeypatch):
    account_id = uuid.uuid4()
    _seed_subscription(db_session, account_id)
    monkeypatch.setattr("app.events.stripe_consumer.SessionLocal", lambda: db_session)

    raw_event = _raw_stripe_event("evt_test3", "invoice.payment_failed", {"id": "in_test3", "customer": "cus_test123", "amount_due": 2900})
    _handle_stripe_event(raw_event)

    sub = db_session.query(Subscription).filter(Subscription.account_id == account_id).one()
    assert sub.status == "past_due"
    assert sub.grace_period_ends_at is not None


def test_unknown_customer_raises_and_does_not_mark_processed(db_session, monkeypatch):
    monkeypatch.setattr("app.events.stripe_consumer.SessionLocal", lambda: db_session)

    raw_event = _raw_stripe_event("evt_test4", "invoice.paid", {"id": "in_test4", "customer": "cus_unknown", "amount_paid": 100})
    try:
        _handle_stripe_event(raw_event)
        assert False, "expected ValueError for unknown customer"
    except ValueError:
        pass

    assert db_session.query(ProcessedEvent).filter(ProcessedEvent.stripe_event_id == "evt_test4").count() == 0