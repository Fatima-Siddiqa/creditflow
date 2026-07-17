import hashlib
import hmac
import json
import time


def _stripe_signature(payload: bytes, secret: str) -> str:
    """Mirrors Stripe's real documented signing scheme (timestamp +
    HMAC-SHA256 of "{timestamp}.{payload}") so stripe.Webhook.construct_event
    verifies it correctly without needing real Stripe test-mode keys."""
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload.decode()}"
    sig = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


def _mock_publish(monkeypatch):
    captured = {}

    async def _fake_publish(exchange_name, event_type, payload, account_id=None):
        captured["exchange_name"] = exchange_name
        captured["event_type"] = event_type
        captured["payload"] = payload

    monkeypatch.setattr("app.api.webhooks.publish_event", _fake_publish)
    return captured


# ---- Stripe ----


def test_stripe_webhook_missing_signature_returns_400(client):
    resp = client.post("/webhooks/stripe", content=b'{"id":"evt_1"}')
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "missing_signature"


def test_stripe_webhook_invalid_signature_returns_400(client, monkeypatch):
    monkeypatch.setattr("app.config.settings.stripe_webhook_secret", "whsec_test")
    resp = client.post(
        "/webhooks/stripe",
        content=b'{"id":"evt_1"}',
        headers={"Stripe-Signature": "t=1,v1=wrongsignature"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "invalid_signature"


def test_stripe_webhook_valid_signature_publishes_and_dedups(client, monkeypatch):
    monkeypatch.setattr("app.config.settings.stripe_webhook_secret", "whsec_test")
    captured = _mock_publish(monkeypatch)

    payload = json.dumps({"id": "evt_test_123", "type": "invoice.payment_succeeded"}).encode()
    sig = _stripe_signature(payload, "whsec_test")

    resp = client.post("/webhooks/stripe", content=payload, headers={"Stripe-Signature": sig})
    assert resp.status_code == 200
    assert resp.json() == {"status": "accepted"}
    assert captured["exchange_name"] == "billing_events"
    assert captured["event_type"] == "billing.webhook_received"
    assert captured["payload"]["source"] == "stripe"

    # Redelivery of the exact same event -> deduped, not republished.
    captured.clear()
    resp2 = client.post("/webhooks/stripe", content=payload, headers={"Stripe-Signature": sig})
    assert resp2.status_code == 200
    assert resp2.json() == {"status": "duplicate_ignored"}
    assert captured == {}


# ---- LinkedIn (placeholder) ----


def test_linkedin_webhook_missing_signature_returns_400(client):
    resp = client.post("/webhooks/linkedin", content=b'{"id":"evt_1"}')
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "missing_signature"


def test_linkedin_webhook_returns_400_when_no_secret_configured(client):
    resp = client.post(
        "/webhooks/linkedin", content=b'{"id":"evt_1"}', headers={"X-LinkedIn-Signature": "whatever"}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "webhook_not_configured"


def test_linkedin_webhook_valid_signature_publishes(client, monkeypatch):
    monkeypatch.setattr("app.config.settings.linkedin_webhook_secret", "li_test_secret")
    captured = _mock_publish(monkeypatch)

    payload = json.dumps({"id": "li_evt_1"}).encode()
    sig = hmac.new(b"li_test_secret", payload, hashlib.sha256).hexdigest()

    resp = client.post("/webhooks/linkedin", content=payload, headers={"X-LinkedIn-Signature": sig})
    assert resp.status_code == 200
    assert captured["exchange_name"] == "social_events"
    assert captured["event_type"] == "social.webhook_received"


# ---- OpenRouter (placeholder) ----


def test_openrouter_webhook_valid_signature_publishes(client, monkeypatch):
    monkeypatch.setattr("app.config.settings.openrouter_webhook_secret", "or_test_secret")
    captured = _mock_publish(monkeypatch)

    payload = json.dumps({"id": "or_evt_1"}).encode()
    sig = hmac.new(b"or_test_secret", payload, hashlib.sha256).hexdigest()

    resp = client.post("/webhooks/openrouter", content=payload, headers={"X-OpenRouter-Signature": sig})
    assert resp.status_code == 200
    assert captured["exchange_name"] == "ai_events"
    assert captured["event_type"] == "ai.webhook_received"


def test_event_id_falls_back_to_content_hash_when_no_id_field(client, monkeypatch):
    """Confirms dedup still works even for a payload shape with no
    id/event_id field — the realistic case for the two placeholder
    sources, whose real shape isn't confirmed."""
    monkeypatch.setattr("app.config.settings.openrouter_webhook_secret", "or_test_secret")
    _mock_publish(monkeypatch)

    payload = json.dumps({"some": "field", "no": "id here"}).encode()
    sig = hmac.new(b"or_test_secret", payload, hashlib.sha256).hexdigest()
    headers = {"X-OpenRouter-Signature": sig}

    first = client.post("/webhooks/openrouter", content=payload, headers=headers)
    second = client.post("/webhooks/openrouter", content=payload, headers=headers)

    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "duplicate_ignored"}