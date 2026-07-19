import uuid

import pytest

from app.events.billing_consumer import apply_invoice_paid
from app.models import Account, AccountMember


def _fake_event(account_id=None, plan_tier="pro", amount=2900, event_id=None):
    return {
        "event_id": str(event_id or uuid.uuid4()),
        "event_type": "invoice.paid",
        "account_id": str(account_id) if account_id else None,
        "producer": "billing-service",
        "schema_version": 1,
        "payload": {
            "account_id": str(account_id or uuid.uuid4()),
            "plan_tier": plan_tier,
            "amount": amount,
        },
    }


def _seed_account(db_session, plan_tier="free"):
    account = Account(type="team", name="Acme", plan_tier=plan_tier)
    db_session.add(account)
    db_session.flush()
    return account


def test_invoice_paid_updates_plan_tier(db_session):
    account = _seed_account(db_session, plan_tier="free")
    event = _fake_event(account_id=account.id, plan_tier="pro")

    processed = apply_invoice_paid(db_session, event)
    db_session.flush()

    assert processed is True
    db_session.refresh(account)
    assert account.plan_tier == "pro"


def test_duplicate_event_id_is_a_noop(db_session):
    account = _seed_account(db_session, plan_tier="free")
    event_id = uuid.uuid4()
    event = _fake_event(account_id=account.id, plan_tier="pro", event_id=event_id)

    first = apply_invoice_paid(db_session, event)
    db_session.flush()
    account.plan_tier = "free"  # simulate something else changing it back between deliveries
    db_session.flush()
    second = apply_invoice_paid(db_session, event)
    db_session.flush()

    assert first is True
    assert second is False
    # The second (duplicate) delivery must NOT re-apply — this is the
    # actual idempotency guarantee, not just "didn't crash twice."
    db_session.refresh(account)
    assert account.plan_tier == "free"


def test_unknown_account_raises_and_does_not_mark_processed(db_session):
    """Missing account: this should surface as a real failure (so the
    standard retry/DLQ path in run_consumer handles it), not be silently
    swallowed as 'handled'. Raising rolls back the whole transaction,
    including the processed_events insert — confirmed here by checking
    that a SECOND call with the same event_id is treated as fresh, not a
    duplicate, since the first one never actually committed."""
    event_id = uuid.uuid4()
    event = _fake_event(account_id=uuid.uuid4(), plan_tier="pro", event_id=event_id)

    with pytest.raises(ValueError, match="unknown account"):
        apply_invoice_paid(db_session, event)
    db_session.rollback()

    # Retried with the SAME event_id — since the first attempt's
    # processed_events insert was rolled back, this must NOT be treated
    # as a duplicate. (Still raises again here since the account still
    # doesn't exist — that's expected; the point is it's not silently
    # marked processed.)
    with pytest.raises(ValueError, match="unknown account"):
        apply_invoice_paid(db_session, event)


def test_seat_count_is_not_touched(db_session):
    """Documents the scope decision explicitly: plan_tier changes, seat
    count (derived from account_members, not a stored column) does not —
    there's nothing on Account for this consumer to write for it."""
    account = _seed_account(db_session, plan_tier="free")
    db_session.add(AccountMember(account_id=account.id, user_id=uuid.uuid4(), role="owner"))
    db_session.flush()

    apply_invoice_paid(db_session, _fake_event(account_id=account.id, plan_tier="team"))
    db_session.flush()

    # No seat-count-related column exists on Account to assert against —
    # this test's real assertion is that apply_invoice_paid doesn't touch
    # account_members at all.
    assert db_session.query(AccountMember).filter(AccountMember.account_id == account.id).count() == 1