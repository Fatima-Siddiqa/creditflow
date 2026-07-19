import uuid

from app.models import Subscription


def _auth(make_token, test_redis_client, jti, sub, account_id, role="owner"):
    token = make_token(jti=jti, sub=sub, account_id=account_id, role=role)
    test_redis_client.setex(f"jti:{jti}", 900, "1")
    return {"Authorization": f"Bearer {token}"}


def test_checkout_session_creates_subscription_row(client, make_token, test_redis_client, db_session, mock_stripe):
    account_id = str(uuid.uuid4())
    headers = _auth(make_token, test_redis_client, "b1", str(uuid.uuid4()), account_id)

    resp = client.post("/billing/checkout-session", json={"plan_tier": "pro"}, headers=headers)

    assert resp.status_code == 201
    assert resp.json()["checkout_url"] == "https://checkout.stripe.com/fake-session"
    assert mock_stripe["create_checkout_session"] == ("cus_fake123", "pro")

    sub = db_session.query(Subscription).filter(Subscription.account_id == uuid.UUID(account_id)).one()
    assert sub.plan_tier == "free"  # only flips to pro once Stripe confirms via webhook, not at checkout creation


def test_checkout_session_rejects_non_owner(client, make_token, test_redis_client, mock_stripe):
    headers = _auth(make_token, test_redis_client, "b2", str(uuid.uuid4()), str(uuid.uuid4()), role="member")
    resp = client.post("/billing/checkout-session", json={"plan_tier": "pro"}, headers=headers)
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "insufficient_role"


def test_checkout_session_rejects_invalid_plan(client, make_token, test_redis_client, mock_stripe):
    headers = _auth(make_token, test_redis_client, "b3", str(uuid.uuid4()), str(uuid.uuid4()))
    resp = client.post("/billing/checkout-session", json={"plan_tier": "enterprise"}, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "invalid_plan"


def test_upgrade_requires_existing_subscription(client, make_token, test_redis_client, mock_stripe):
    headers = _auth(make_token, test_redis_client, "b4", str(uuid.uuid4()), str(uuid.uuid4()))
    resp = client.post("/billing/upgrade", json={"plan_tier": "team"}, headers=headers)
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "no_active_subscription"


def test_list_invoices_empty(client, make_token, test_redis_client):
    headers = _auth(make_token, test_redis_client, "b5", str(uuid.uuid4()), str(uuid.uuid4()))
    resp = client.get("/billing/invoices", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []