import uuid

from app.events.billing_consumer import apply_invoice_paid, apply_refund_issued
from app.models.ledger import CreditLedger, TransactionType


def _invoice_paid_event(account_id, plan_tier="pro", event_id=None):
    return {
        "event_id": str(event_id or uuid.uuid4()),
        "event_type": "invoice.paid",
        "account_id": account_id,
        "producer": "billing-service",
        "schema_version": 1,
        "payload": {"account_id": account_id, "amount_cents": 2900, "plan_tier": plan_tier},
    }


def _refund_issued_event(account_id, event_id=None):
    return {
        "event_id": str(event_id or uuid.uuid4()),
        "event_type": "refund.issued",
        "account_id": account_id,
        "producer": "billing-service",
        "schema_version": 1,
        "payload": {"account_id": account_id, "stripe_refund_id": "re_fake123", "amount_cents": 2900, "reason": "requested_by_customer"},
    }


# --- API endpoint tests -----------------------------------------------

def test_get_empty_balance(client, auth_headers):
    headers = auth_headers(account_id="acc_empty")
    response = client.get("/credits/balance", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"account_id": "acc_empty", "balance": 0}


def test_balance_reflects_ledger(client, auth_headers, db_session):
    account_id = "acc_with_credits"
    db_session.add(CreditLedger(id=str(uuid.uuid4()), account_id=account_id, amount=500, transaction_type=TransactionType.PURCHASE))
    db_session.commit()

    headers = auth_headers(account_id=account_id)
    response = client.get("/credits/balance", headers=headers)
    assert response.status_code == 200
    assert response.json()["balance"] == 500


def test_marketplace_listing_insufficient_funds(client, auth_headers):
    headers = auth_headers(account_id="acc_broke")
    response = client.post("/credits/marketplace", json={"amount": 500, "price_cents": 1000}, headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "insufficient_credits"


def test_marketplace_listing_success_escrows_credits(client, auth_headers, db_session):
    account_id = "acc_seller"
    db_session.add(CreditLedger(id=str(uuid.uuid4()), account_id=account_id, amount=1000, transaction_type=TransactionType.PURCHASE))
    db_session.commit()

    headers = auth_headers(account_id=account_id)
    response = client.post("/credits/marketplace", json={"amount": 300, "price_cents": 1500}, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "active"

    balance = client.get("/credits/balance", headers=headers).json()["balance"]
    assert balance == 700  # 1000 granted - 300 escrowed for the listing


def test_balance_requires_auth(client):
    response = client.get("/credits/balance")
    assert response.status_code == 401


# --- billing_consumer idempotency/logic tests --------------------------

def test_invoice_paid_credits_the_ledger(db_session):
    account_id = "acc_1"
    applied = apply_invoice_paid(db_session, _invoice_paid_event(account_id, plan_tier="pro"))
    db_session.flush()

    assert applied is True
    balance = db_session.query(CreditLedger).filter(CreditLedger.account_id == account_id).one()
    assert balance.amount == 1000
    assert balance.transaction_type == TransactionType.PURCHASE


def test_invoice_paid_duplicate_event_is_a_noop(db_session):
    account_id = "acc_2"
    event = _invoice_paid_event(account_id, plan_tier="team", event_id=uuid.uuid4())

    first = apply_invoice_paid(db_session, event)
    db_session.flush()
    second = apply_invoice_paid(db_session, event)  # redelivery, same event_id
    db_session.flush()

    assert first is True
    assert second is False
    entries = db_session.query(CreditLedger).filter(CreditLedger.account_id == account_id).all()
    assert len(entries) == 1  # not double-credited


def test_refund_claws_back_last_purchase(db_session):
    account_id = "acc_3"
    apply_invoice_paid(db_session, _invoice_paid_event(account_id, plan_tier="pro"))
    db_session.flush()

    applied = apply_refund_issued(db_session, _refund_issued_event(account_id))
    db_session.flush()

    assert applied is True
    total = sum(e.amount for e in db_session.query(CreditLedger).filter(CreditLedger.account_id == account_id).all())
    assert total == 0  # 1000 granted, 1000 clawed back