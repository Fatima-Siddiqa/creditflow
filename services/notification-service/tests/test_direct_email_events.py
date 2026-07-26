import uuid

import respx
from httpx import Response

from app.config import settings
from app.dispatcher import handle_event


def _event(event_type: str, payload: dict, event_id: str | None = None) -> dict:
    return {"event_id": event_id or str(uuid.uuid4()), "event_type": event_type, "payload": payload}


@respx.mock
async def test_user_registered_sends_verification_email(notification_logs):
    send_route = respx.post(f"{settings.email_provider_base_url}/emails").mock(return_value=Response(200, json={"id": "email_1"}))

    processed = await handle_event(_event("user.registered", {
        "user_id": "u1", "email": "alice@example.com", "verification_token": "tok123",
    }))

    assert processed is True
    assert send_route.called
    sent_payload = send_route.calls[0].request.content
    assert b"alice@example.com" in sent_payload

    logs = notification_logs()
    assert len(logs) == 1
    assert logs[0]["type"] == "user.registered"
    assert logs[0]["recipient"] == "alice@example.com"
    assert logs[0]["status"] == "sent"


@respx.mock
async def test_password_reset_requested_sends_otp_email(notification_logs):
    respx.post(f"{settings.email_provider_base_url}/emails").mock(return_value=Response(200, json={"id": "email_2"}))

    processed = await handle_event(_event("user.password_reset_requested", {
        "user_id": "u1", "email": "bob@example.com", "otp": "654321",
    }))

    assert processed is True
    logs = notification_logs()
    assert logs[0]["recipient"] == "bob@example.com"
    assert logs[0]["status"] == "sent"


@respx.mock
async def test_invite_created_sends_invite_email(notification_logs):
    respx.post(f"{settings.email_provider_base_url}/emails").mock(return_value=Response(200, json={"id": "email_3"}))

    processed = await handle_event(_event("invite.created", {
        "invite_id": "inv1", "account_id": "acc1", "email": "carol@example.com", "role": "member",
    }))

    assert processed is True
    logs = notification_logs()
    assert logs[0]["recipient"] == "carol@example.com"
    assert logs[0]["status"] == "sent"


async def test_unregistered_event_type_is_skipped(notification_logs):
    processed = await handle_event(_event("some.unhandled.event", {"foo": "bar"}))
    assert processed is False
    assert notification_logs() == []