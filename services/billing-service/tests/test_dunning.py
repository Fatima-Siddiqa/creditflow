import uuid
from datetime import datetime, timedelta, timezone

from app.dunning import _check_overdue_subscriptions
from app.models import OutboxEvent, Subscription


def test_overdue_subscription_gets_downgraded(db_session, monkeypatch):
    account_id = uuid.uuid4()
    sub = Subscription(
        account_id=account_id, stripe_customer_id="cus_x", plan_tier="pro",
        status="past_due", grace_period_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(sub)
    db_session.commit()

    monkeypatch.setattr("app.dunning.SessionLocal", lambda: db_session)
    _check_overdue_subscriptions()

    db_session.expire_all()
    updated = db_session.query(Subscription).filter(Subscription.account_id == account_id).one()
    assert updated.status == "downgraded"
    assert updated.plan_tier == "free"

    events = db_session.query(OutboxEvent).filter(OutboxEvent.event_type == "subscription.downgraded").all()
    assert len(events) == 1


def test_subscription_within_grace_period_is_untouched(db_session, monkeypatch):
    account_id = uuid.uuid4()
    sub = Subscription(
        account_id=account_id, stripe_customer_id="cus_y", plan_tier="pro",
        status="past_due", grace_period_ends_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    db_session.add(sub)
    db_session.commit()

    monkeypatch.setattr("app.dunning.SessionLocal", lambda: db_session)
    _check_overdue_subscriptions()

    db_session.expire_all()
    unchanged = db_session.query(Subscription).filter(Subscription.account_id == account_id).one()
    assert unchanged.status == "past_due"