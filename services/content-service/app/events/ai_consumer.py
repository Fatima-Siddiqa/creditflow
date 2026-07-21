import asyncio
import json
import logging
import uuid

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.events.publisher import publish_event
from app.models.content import Content, ContentStatus, ContentVersion

logger = logging.getLogger("ai_consumer")

SOURCE_EXCHANGE = "ai_events"
QUEUE_NAME = "content-service.ai_events"
DLX_NAME = f"{QUEUE_NAME}.dlx"
DLQ_NAME = f"{QUEUE_NAME}.dlq"
MAX_RETRIES = 3


def apply_generation_completed(db: Session, event: dict) -> bool:
    """Only builds a draft when content_type == 'post' -- a 'chat'
    generation (or any other content_type) is a documented no-op, not
    an error, per Phase 9's test list."""
    event_id = event["event_id"]
    payload = event["payload"]

    inserted = db.execute(
        text("INSERT INTO content.processed_events (event_id) VALUES (:event_id) ON CONFLICT DO NOTHING RETURNING event_id"),
        {"event_id": event_id},
    ).fetchone()
    if inserted is None:
        logger.info("event %s already processed, skipping", event_id)
        return False

    if payload.get("content_type") != "post":
        return False

    account_id = payload["account_id"]
    content_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(Content(id=content_id, account_id=account_id, created_by_user_id=account_id,
                    status=ContentStatus.DRAFT, current_version_id=version_id))
    db.add(ContentVersion(id=version_id, content_id=content_id, body=payload.get("response_text", ""),
                           created_by_user_id=account_id))
    return True


HANDLERS = {"ai.generation_completed": apply_generation_completed}


def _handle_event(event: dict) -> tuple[bool, str | None]:
    handler = HANDLERS.get(event.get("event_type"))
    if handler is None:
        return False, None
    db = SessionLocal()
    try:
        applied = handler(db, event)
        db.commit()
        return applied, event["payload"]["account_id"]
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def _setup_topology(channel: aio_pika.Channel) -> tuple[aio_pika.Queue, aio_pika.Exchange]:
    exchange = await channel.declare_exchange(SOURCE_EXCHANGE, ExchangeType.TOPIC, durable=True)
    dlx = await channel.declare_exchange(DLX_NAME, ExchangeType.FANOUT, durable=True)
    dlq = await channel.declare_queue(DLQ_NAME, durable=True)
    await dlq.bind(dlx)
    queue = await channel.declare_queue(QUEUE_NAME, durable=True, arguments={"x-dead-letter-exchange": DLX_NAME})
    await queue.bind(exchange, routing_key="ai.generation_completed")
    return queue, exchange


async def _process_message(message: aio_pika.IncomingMessage, exchange: aio_pika.Exchange) -> None:
    event = json.loads(message.body)
    if event.get("event_type") not in HANDLERS:
        await message.ack()
        return

    try:
        applied, account_id = await asyncio.to_thread(_handle_event, event)
        await message.ack()
    except Exception:
        logger.exception("failed to process event %s", event.get("event_id"))
        retry_count = (message.headers or {}).get("x-retry-count", 0)
        if retry_count < MAX_RETRIES:
            await exchange.publish(
                Message(body=message.body, delivery_mode=DeliveryMode.PERSISTENT,
                        headers={"x-retry-count": retry_count + 1}, content_type="application/json"),
                routing_key=message.routing_key,
            )
            await message.ack()
        else:
            logger.error("event %s exceeded max retries, routing to DLQ", event.get("event_id"))
            await message.reject(requeue=False)
        return

    if applied:
        try:
            await publish_event("content.created", {"account_id": account_id, "status": "draft"}, account_id=account_id)
        except Exception:
            logger.exception("created draft for account %s but failed to publish content.created", account_id)


async def run_consumer() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)
    queue, exchange = await _setup_topology(channel)
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await _process_message(message, exchange)