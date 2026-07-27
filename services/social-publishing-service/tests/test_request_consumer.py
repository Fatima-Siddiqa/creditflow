import json
import uuid
from unittest.mock import AsyncMock

import pytest

from app.events import request_consumer
from app.job_runner import execute_job


class FakeMessage:
    """Minimal stand-in for aio_pika.IncomingMessage -- real one needs a
    live channel, which these unit tests deliberately avoid."""
    def __init__(self, event: dict, headers: dict | None = None, routing_key="scrape.requested"):
        self.body = json.dumps(event).encode()
        self.headers = headers or {}
        self.routing_key = routing_key
        self.ack = AsyncMock()
        self.reject = AsyncMock()


def _event(event_id=None, target_url="https://example.com", account_id="acct-1"):
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": "scrape.requested",
        "payload": {"target_url": target_url, "job_type": "trend_check", "account_id": account_id},
    }


async def test_first_delivery_creates_job_and_acks(monkeypatch, _mongo_mock):
    monkeypatch.setattr(request_consumer, "execute_job", AsyncMock())
    exchange = AsyncMock()
    event = _event()

    await request_consumer._process_message(FakeMessage(event), exchange)

    request_consumer.execute_job.assert_awaited_once()
    assert request_consumer.scrape_jobs.count_documents({"source": "event"}) == 1


async def test_redelivered_event_id_is_acked_without_reprocessing(monkeypatch, _mongo_mock):
    fake_execute = AsyncMock()
    monkeypatch.setattr(request_consumer, "execute_job", fake_execute)
    exchange = AsyncMock()
    event = _event(event_id="dup-event-1")

    msg1 = FakeMessage(event)
    await request_consumer._process_message(msg1, exchange)
    msg1.ack.assert_awaited_once()

    msg2 = FakeMessage(event)  # simulates RabbitMQ redelivering the same message
    await request_consumer._process_message(msg2, exchange)

    fake_execute.assert_awaited_once()  # still only ran once
    msg2.ack.assert_awaited_once()  # second delivery is still acked, just skipped
    assert request_consumer.scrape_jobs.count_documents({"source": "event"}) == 1


async def test_failure_republishes_with_incremented_retry_header(monkeypatch, _mongo_mock):
    monkeypatch.setattr(request_consumer, "execute_job", AsyncMock(side_effect=RuntimeError("boom")))
    exchange = AsyncMock()
    event = _event()
    message = FakeMessage(event, headers={"x-retry-count": 1})

    await request_consumer._process_message(message, exchange)

    exchange.publish.assert_awaited_once()
    published_msg = exchange.publish.await_args.args[0]
    assert published_msg.headers["x-retry-count"] == 2
    message.ack.assert_awaited_once()  # original acked -- superseded by the republish
    message.reject.assert_not_called()


async def test_failure_at_max_retries_dead_letters_instead_of_republishing(monkeypatch, _mongo_mock):
    monkeypatch.setattr(request_consumer, "execute_job", AsyncMock(side_effect=RuntimeError("boom")))
    exchange = AsyncMock()
    event = _event()
    message = FakeMessage(event, headers={"x-retry-count": request_consumer.MAX_RETRIES})

    await request_consumer._process_message(message, exchange)

    exchange.publish.assert_not_called()
    message.reject.assert_awaited_once_with(requeue=False)
    message.ack.assert_not_called()