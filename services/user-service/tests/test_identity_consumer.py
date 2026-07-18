import uuid

from app.events.identity_consumer import create_account_for_registered_user
from app.models import Account, AccountMember


def _fake_event(user_id=None, event_id=None):
    return {
        "event_id": str(event_id or uuid.uuid4()),
        "event_type": "user.registered",
        "account_id": None,
        "producer": "auth-service",
        "schema_version": 1,
        "payload": {"user_id": str(user_id or uuid.uuid4()), "email": "a@b.com"},
    }


def test_creates_individual_account_and_owner_membership(db_session):
    user_id = uuid.uuid4()
    event = _fake_event(user_id=user_id)

    processed = create_account_for_registered_user(db_session, event)
    db_session.flush()

    assert processed is True
    account = db_session.query(Account).one()
    assert account.type == "individual"

    membership = db_session.query(AccountMember).one()
    assert membership.account_id == account.id
    assert membership.user_id == user_id
    assert membership.role == "owner"


def test_duplicate_event_id_is_a_noop(db_session):
    user_id = uuid.uuid4()
    event_id = uuid.uuid4()
    event = _fake_event(user_id=user_id, event_id=event_id)

    first = create_account_for_registered_user(db_session, event)
    db_session.flush()
    second = create_account_for_registered_user(db_session, event)
    db_session.flush()

    assert first is True
    assert second is False
    # Only one account/membership pair exists despite two calls with the
    # same event_id — this is the idempotency guarantee itself, not just
    # "it didn't crash."
    assert db_session.query(Account).count() == 1
    assert db_session.query(AccountMember).count() == 1


def test_different_event_ids_for_same_user_both_create_accounts(db_session):
    """Deliberately documents a real limitation, not a bug: idempotency
    here is keyed on event_id, not on user_id. If auth-service ever
    re-published a genuinely NEW user.registered event for a user who
    already has an account (nothing currently prevents this, though
    auth-service's own signup flow has no code path that would trigger
    it), this consumer would create a second individual account. Guarding
    against that is a business-logic concern, not something the
    idempotency pattern itself is meant to solve — noting it here so it
    doesn't get silently assumed away."""
    user_id = uuid.uuid4()
    create_account_for_registered_user(db_session, _fake_event(user_id=user_id))
    db_session.flush()
    create_account_for_registered_user(db_session, _fake_event(user_id=user_id))
    db_session.flush()

    assert db_session.query(Account).count() == 2