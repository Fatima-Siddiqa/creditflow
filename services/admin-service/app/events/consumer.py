import asyncio
import json
import logging
import uuid

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal

logger = logging.getLogger("admin_consumer")

MAX_RETRIES = 3

# Every exchange in the platform (Phase 1 topology) — the one deliberate
# wildcard "#" subscriber, per PHASE_14 and spec §8 Service 13.
EXCHANGES = [
    "identity_events", "account_events", "billing_events", "credits_events",
    "usage_events", "ai_events", "content_events", "social_events",
    "scraper_events", "notification_events",
]


def _write_audit_row(event: dict) -> bool:
    """Synchronous by nature (SQLAlchemy) -- always call this via
    asyncio.to_thread from the consumer loop, never directly, since this
    service gathers 10 exchange bindings on one event loop and a blocking
    call here would stall all of them at once. Returns True/False so
    tests/test_audit_consumer.py can keep asserting on it directly,
    bypassing the RabbitMQ layer entirely."""
    db = SessionLocal()
    try:
        inserted = db.execute(
            text(
                "INSERT INTO admin.processed_events (event_id) VALUES (:eid) "
                "ON CONFLICT DO NOTHING RETURNING event_id"
            ),
            {"eid": event.get("event_id")},
        ).fetchone()
        if inserted is None:
            return False  # already processed -- caller still acks either way
        db.execute(
            text(
                "INSERT INTO admin.audit_log (event_id, event_type, account_id, payload, occurred_at) "
                "VALUES (:eid, :etype, :acc, :payload, :occurred)"
            ),
            {
                "eid": event.get("event_id"),
                "etype": event.get("event_type"),
                "acc": event.get("account_id"),
                "payload": json.dumps(event.get("payload", {})),
                "occurred": event.get("occurred_at"),
            },
        )
        db.commit()
        return True
    finally:
        db.close()


async def _bind_exchange(channel: aio_pika.Channel, exchange_name: str) -> None:
    exchange = await channel.declare_exchange(exchange_name, ExchangeType.TOPIC, durable=True)
    queue_name = f"admin-service.{exchange_name}.all"
    dlx = await channel.declare_exchange(f"{queue_name}.dlx", ExchangeType.FANOUT, durable=True)
    dlq = await channel.declare_queue(f"{queue_name}.dlq", durable=True)
    await dlq.bind(dlx)
    queue = await channel.declare_queue(queue_name, durable=True, arguments={"x-dead-letter-exchange": f"{queue_name}.dlx"})
    await queue.bind(exchange, routing_key="#")  # wildcard — audit needs everything

    async with queue.iterator() as it:
        async for message in it:
            event = json.loads(message.body)
            try:
                await asyncio.to_thread(_write_audit_row, event)
                await message.ack()
            except Exception:
                logger.exception("failed to audit event %s", event.get("event_id"))
                retry_count = (message.headers or {}).get("x-retry-count", 0)
                if retry_count < MAX_RETRIES:
                    retry_event = dict(event)
                    retry_event["event_id"] = str(uuid.uuid4())  # fresh id -- original was never marked processed
                    await exchange.publish(
                        Message(
                            body=json.dumps(retry_event).encode(),
                            delivery_mode=DeliveryMode.PERSISTENT,
                            headers={"x-retry-count": retry_count + 1},
                            content_type="application/json",
                        ),
                        routing_key=message.routing_key,
                    )
                    await message.ack()
                else:
                    await message.reject(requeue=False)


async def run_consumer() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=20)
    await asyncio.gather(*[_bind_exchange(channel, ex) for ex in EXCHANGES])