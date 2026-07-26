import uuid

import respx
from httpx import Response

from app.config import settings
from app.dispatcher import handle_event


def _event(event_type: str, payload: dict, event_id: str | None = None) -> dict:
    return {"event_id": event_id or str(uuid.uuid4()), "event_type": event_type, "payload": payload}


def _mock_owner_and_email(account_id="acc1", user_id="user1", email="owner@example.com"):
    respx.get(f"{settings.user_service_url}/accounts/internal/{account_id}/owner").mock(
        return_value=Response(200, json={"account_id": account_id, "user_id": user_id, "role": "owner"})
    )
    respx.get(f"{settings.auth_service_url}/auth/internal/users/{user_id}").mock(
        return_value=Response(200, json={"user_id": user_id, "email": email})
    )


@respx.mock
async def test_invoice_paid_resolves_owner_and_sends_receipt(notification_logs):
    _mock_owner_and_email()
    respx.post(f"{settings.email_provider_base_url}/emails").mock(return_value=Response(200, json={"id": "e1"}))

    processed = await handle_event(_event("invoice.paid", {"account_id": "acc1", "amount_cents": 2500, "plan_tier": "pro"}))

    assert processed is True
    logs = notification_logs()
    assert logs[0]["recipient"] == "owner@example.com"
    assert logs[0]["status"] == "sent"


@respx.mock
async def test_payment_failed_resolves_owner_and_sends_alert(notification_logs):
    _mock_owner_and_email()
    respx.post(f"{settings.email_provider_base_url}/emails").mock(return_value=Response(200, json={"id": "e2"}))

    processed = await handle_event(_event("payment.failed", {"account_id": "acc1"}))

    assert processed is True
    assert notification_logs()[0]["recipient"] == "owner@example.com"


@respx.mock
async def test_member_joined_resolves_user_email_directly(notification_logs):
    respx.get(f"{settings.auth_service_url}/auth/internal/users/user1").mock(
        return_value=Response(200, json={"user_id": "user1", "email": "member@example.com"})
    )
    respx.post(f"{settings.email_provider_base_url}/emails").mock(return_value=Response(200, json={"id": "e3"}))

    processed = await handle_event(_event("member.joined", {"account_id": "acc1", "user_id": "user1", "role": "member"}))

    assert processed is True
    assert notification_logs()[0]["recipient"] == "member@example.com"


@respx.mock
async def test_post_published_and_post_failed(notification_logs):
    _mock_owner_and_email()
    respx.post(f"{settings.email_provider_base_url}/emails").mock(return_value=Response(200, json={"id": "e4"}))

    await handle_event(_event("post.published", {"account_id": "acc1"}))
    await handle_event(_event("post.failed", {"account_id": "acc1", "reason": "token expired"}))

    logs = notification_logs()
    assert len(logs) == 2
    assert {log["type"] for log in logs} == {"post.published", "post.failed"}
    assert all(log["recipient"] == "owner@example.com" for log in logs)


@respx.mock
async def test_usage_threshold_reached_sends_alert(notification_logs):
    _mock_owner_and_email()
    respx.post(f"{settings.email_provider_base_url}/emails").mock(return_value=Response(200, json={"id": "e5"}))

    processed = await handle_event(_event("usage.threshold_reached", {"account_id": "acc1", "threshold": 80, "period": "2026-07"}))

    assert processed is True
    assert notification_logs()[0]["type"] == "usage.threshold_reached"


@respx.mock
async def test_recipient_resolution_failure_is_logged_not_raised(notification_logs):
    respx.get(f"{settings.user_service_url}/accounts/internal/acc1/owner").mock(return_value=Response(404))

    processed = await handle_event(_event("invoice.paid", {"account_id": "acc1", "amount_cents": 100}))

    assert processed is True
    logs = notification_logs()
    assert logs[0]["status"] == "failed"
    assert logs[0]["recipient"] == "unknown"