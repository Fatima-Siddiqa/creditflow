import asyncio
import json
import logging

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from app.config import settings
from app.dispatcher import handle_event
from app.events.publisher import publish_event as publish_notification_event

logger = logging.getLogger("notification_consumer")

MAX_RETRIES = 3

# One binding per (source exchange, routing key) this service cares about.
# Verified against each publisher's actual code, not the phase plan's
# assumed exchange names (auth-service publishes to identity_events, not
# auth_events).
BINDINGS: list[tuple[str, str]] = [
    ("identity_events", "user.registered"),
    ("identity_events", "user.password_reset_requested"),
    ("billing_events", "invoice.paid"),
    ("billing_events", "payment.failed"),
    ("account_events", "member.joined"),
    ("account_events", "invite.created"),
    ("social_events", "post.published"),
    ("social_events", "post.failed"),
    ("usage_events", "usage.threshold_reached"),
]


async def _run_single_binding(channel: aio_pika.Channel, source_exchange: str, routing_key: str) -> None:
    """One queue per (exchange, routing_key) pair -- keeps retry/DLQ
    unambiguous and matches every other service's one-queue-per-source
    convention."""
    exchange = await channel.declare_exchange(source_exchange, ExchangeType.TOPIC, durable=True)

    queue_name = f"notification-service.{source_exchange}.{routing_key}"
    dlx_name = f"{queue_name}.dlx"
    dlq_name = f"{queue_name}.dlq"

    dlx = await channel.declare_exchange(dlx_name, ExchangeType.FANOUT, durable=True)
    dlq = await channel.declare_queue(dlq_name, durable=True)
    await dlq.bind(dlx)

    queue = await channel.declare_queue(queue_name, durable=True, arguments={"x-dead-letter-exchange": dlx_name})
    await queue.bind(exchange, routing_key=routing_key)

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await _process_message(message, exchange, routing_key)


async def _process_message(message: aio_pika.IncomingMessage, exchange: aio_pika.Exchange, routing_key: str) -> None:
    event = json.loads(message.body)
    try:
        processed = await handle_event(event)
        await message.ack()
    except Exception:
        logger.exception("failed to process event %s (%s)", event.get("event_id"), routing_key)
        retry_count = (message.headers or {}).get("x-retry-count", 0)
        if retry_count < MAX_RETRIES:
            await exchange.publish(
                Message(
                    body=message.body,
                    delivery_mode=DeliveryMode.PERSISTENT,
                    headers={"x-retry-count": retry_count + 1},
                    content_type="application/json",
                ),
                routing_key=routing_key,
            )
            await message.ack()
        else:
            logger.error("event %s exceeded max retries, routing to DLQ", event.get("event_id"))
            await message.reject(requeue=False)
        return

    if processed:
        try:
            await publish_notification_event("notification.sent", {"event_type": event.get("event_type")})
        except Exception:
            logger.exception("processed %s but failed to publish notification.sent", event.get("event_id"))


async def run_consumer() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)

    tasks = [
        asyncio.create_task(_run_single_binding(channel, source_exchange, routing_key))
        for source_exchange, routing_key in BINDINGS
    ]
    await asyncio.gather(*tasks)