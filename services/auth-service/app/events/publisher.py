import json
import uuid
from datetime import datetime, timezone
from typing import Any

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from app.config import settings

EXCHANGE_NAME = "identity_events"


async def publish_event(event_type: str, payload: dict[str, Any], account_id: uuid.UUID | None = None) -> None:
    """Opens a short-lived connection, publishes one event, closes.
    Fine for this service's low-frequency auth events; a persistent
    connection pool is unnecessary complexity here."""
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    try:
        # publisher confirms are on by default with a channel opened this way
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
        )

        envelope = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "account_id": str(account_id) if account_id else None,
            "producer": "auth-service",
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