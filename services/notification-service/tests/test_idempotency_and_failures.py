import uuid

import respx
from httpx import Response

from app.config import settings
from app.dispatcher import handle_event


def _event(event_type: str, payload: dict, event_id: str | None = None) -> dict:
    return {"event_id": event_id or str(uuid.uuid4()), "event_type": event_type, "payload": payload}


@respx.mock
async def test_duplicate_event_delivery_sends_only_once(notification_logs):
    send_route = respx.post(f"{settings.email_provider_base_url}/emails").mock(return_value=Response(200, json={"id": "e1"}))

    event_id = str(uuid.uuid4())
    event = _event("user.registered", {"user_id": "u1", "email": "dup@example.com", "verification_token": "tok"}, event_id=event_id)

    first = await handle_event(event)
    second = await handle_event(event)

    assert first is True
    assert second is False
    assert send_route.call_count == 1
    assert len(notification_logs()) == 1


@respx.mock
async def test_email_provider_failure_logs_failed_status_without_raising(notification_logs):
    respx.post(f"{settings.email_provider_base_url}/emails").mock(return_value=Response(500, text="provider error"))

    processed = await handle_event(_event("user.registered", {
        "user_id": "u1", "email": "failcase@example.com", "verification_token": "tok",
    }))

    assert processed is True
    logs = notification_logs()
    assert logs[0]["status"] == "failed"
    assert logs[0]["recipient"] == "failcase@example.com"
    assert logs[0]["error"] is not None