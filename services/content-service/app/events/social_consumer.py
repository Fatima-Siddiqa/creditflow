import json
import logging

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.config import settings
from app.db import SessionLocal
from app.models.content import Content, ContentStatus

logger = logging.getLogger("social_consumer")

SOURCE_EXCHANGE = "social_events"
QUEUE_NAME = "content-service.social_events"
DLX_NAME = f"{QUEUE_NAME}.dlx"
DLQ_NAME = f"{QUEUE_NAME}.dlq"


def _mark_processed(db: Session, event_id: str) -> bool:
    inserted = db.execute(
        text("INSERT INTO content.processed_events (event_id) VALUES (:event_id) ON CONFLICT DO NOTHING RETURNING event_id"),
        {"event_id": event_id},
    ).fetchone()
    return inserted is not None


def apply_post_published(db: Session, event: dict) -> bool:
    payload = event["payload"]
    content_id = payload.get("content_id")
    if not content_id:
        logger.warning("post.published event %s missing content_id, cannot update status", event["event_id"])
        return False
    content = db.query(Content).filter(Content.id == content_id).one_or_none()
    if content is None:
        return False
    content.status = ContentStatus.PUBLISHED
    content.updated_at = datetime.now(timezone.utc)
    return True


def apply_post_failed(db: Session, event: dict) -> bool:
    payload = event["payload"]
    content_id = payload.get("content_id")
    if not content_id:
        return False
    content = db.query(Content).filter(Content.id == content_id).one_or_none()
    if content is None:
        return False
    # Deliberately left at APPROVED, not moved back to draft or forward
    # to published -- a failed LinkedIn attempt should stay schedulable/
    # retryable from the Calendar page, not silently disappear or lie
    # about having succeeded.
    content.updated_at = datetime.now(timezone.utc)
    return True


HANDLERS = {"post.published": apply_post_published, "post.failed": apply_post_failed}


def _handle_event(event: dict) -> bool:
    handler = HANDLERS.get(event.get("event_type"))
    if handler is None:
        return False
    db = SessionLocal()
    try:
        if not _mark_processed(db, event["event_id"]):
            logger.info("event %s already processed, skipping", event["event_id"])
            db.commit()
            return False
        applied = handler(db, event)
        db.commit()
        return applied
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
    await queue.bind(exchange, routing_key="post.published")
    await queue.bind(exchange, routing_key="post.failed")
    return queue, exchange


async def _process_message(message: aio_pika.IncomingMessage) -> None:
    event = json.loads(message.body)
    if event.get("event_type") not in HANDLERS:
        await message.ack()
        return
    try:
        _handle_event(event)
        await message.ack()
    except Exception:
        logger.exception("failed to process event %s", event.get("event_id"))
        await message.reject(requeue=False)  # goes to DLQ via x-dead-letter-exchange


async def run_consumer() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)
    queue, _ = await _setup_topology(channel)
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await _process_message(message)