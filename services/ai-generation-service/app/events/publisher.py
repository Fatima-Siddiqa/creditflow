import json
import uuid
from datetime import datetime, timezone
from typing import Any

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from app.config import settings

EXCHANGE_NAME = "ai_events"


async def publish_event(event_type: str, payload: dict[str, Any], account_id: str | None = None) -> None:
    """Opens a short-lived connection, publishes one event, closes.
    Mirrors usage-service's app/events/publisher.py and credits-service's
    -- same low-frequency justification applies here (at most one
    completed/failed event per generation call, not a hot path needing a
    pooled connection).

    IMPORTANT: usage-service's app/events/ai_consumer.py (built Phase 7,
    already live) hard-requires `payload["tokens_used"]` and reads
    `payload.get("cost_cents", 0)` -- see its apply_generation_completed
    docstring, which calls this exact shape its own "documented
    assumption" about Phase 8 pending confirmation. app/generation_worker.py
    is written to always include `tokens_used` (mapped from this job's
    total_tokens) to satisfy that contract -- don't rename that key here
    without also updating usage-service's consumer, or every completion
    event will dead-letter after MAX_RETRIES with a KeyError.
    """
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    try:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
        )

        envelope = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "account_id": account_id,
            "producer": "ai-generation-service",
            "schema_version": 1,
            "payload": payload,
        }

        message = Message(
            body=json.dumps(envelope).encode(),
            delivery_mode=DeliveryMode.PERSISTENT,  # delivery_mode=2, per spec §7
            content_type="application/json",
        )

        await exchange.publish(message, routing_key=event_type)
    finally:
        await connection.close()