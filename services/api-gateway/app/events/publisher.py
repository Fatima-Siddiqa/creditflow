import json
import uuid
from datetime import datetime, timezone
from typing import Any

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from app.config import settings

PRODUCER_NAME = "api-gateway"


async def publish_event(
    exchange_name: str, event_type: str, payload: dict[str, Any], account_id: str | None = None
) -> None:
    """Same envelope/exchange conventions as every other service — see
    docs/EVENT_CONTRACTS.md. One short-lived connection per publish (fine
    at this service's webhook-relay frequency; a persistent pool is
    unnecessary complexity here, same call auth-service made).

    Unlike auth-service (always publishes to identity_events), the
    gateway relays onto whichever domain exchange matches the webhook
    source (billing_events / social_events / ai_events), so exchange_name
    is a parameter rather than a module constant."""
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    try:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(exchange_name, ExchangeType.TOPIC, durable=True)

        envelope = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "account_id": account_id,
            "producer": PRODUCER_NAME,
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