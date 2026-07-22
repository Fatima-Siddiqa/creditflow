import json
import uuid
from datetime import datetime, timezone
from typing import Any

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from app.config import settings

EXCHANGE_NAME = "social_events"


async def publish_event(event_type: str, payload: dict[str, Any], account_id: str | None = None) -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    try:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(EXCHANGE_NAME, ExchangeType.TOPIC, durable=True)
        envelope = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "account_id": account_id,
            "producer": "social-publishing-service",
            "schema_version": 1,
            "payload": payload,
        }
        message = Message(
            body=json.dumps(envelope).encode(),
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
        )
        await exchange.publish(message, routing_key=event_type)
    finally:
        await connection.close()