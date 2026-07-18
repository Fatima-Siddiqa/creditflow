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
from app.models import Account, AccountMember

logger = logging.getLogger("identity_consumer")

EXCHANGE_NAME = "identity_events"
QUEUE_NAME = "user-service.identity_events"
DLX_NAME = f"{QUEUE_NAME}.dlx"
DLQ_NAME = f"{QUEUE_NAME}.dlq"
MAX_RETRIES = 3


def create_account_for_registered_user(db: Session, event: dict) -> bool:
    """Pure business logic, no RabbitMQ or session-lifecycle concerns —
    this is what tests exercise directly. Returns True if this event_id was
    newly processed, False if it was a duplicate (idempotency table already
    had it) and no account was created.

    Per spec §8 Service 3: 'Create an Account automatically on signup
    (type: individual).' The registering user becomes its sole owner.

    Caller owns the transaction boundary — see _handle_user_registered
    below for the real consumer's per-message commit, and
    tests/test_identity_consumer.py for how tests share this same function
    inside their own rollback-wrapped transaction (db_session fixture).
    """
    event_id = uuid.UUID(event["event_id"])
    user_id = uuid.UUID(event["payload"]["user_id"])

    inserted = db.execute(
        text("""
            INSERT INTO tenant.processed_events (event_id)
            VALUES (:event_id)
            ON CONFLICT DO NOTHING
            RETURNING event_id
        """),
        {"event_id": event_id},
    ).fetchone()

    if inserted is None:
        logger.info("event %s already processed, skipping", event_id)
        return False

    account = Account(type="individual", name=None, plan_tier="free")
    db.add(account)
    db.flush()  # assigns account.id before the membership row references it

    db.add(AccountMember(account_id=account.id, user_id=user_id, role="owner"))
    return True


def _handle_user_registered(event: dict) -> None:
    """Runs in a worker thread (see asyncio.to_thread in _process_message)
    — this service's DB layer is synchronous SQLAlchemy, matching every
    other service in the project, not async. Owns its own session and
    commit/rollback, unlike create_account_for_registered_user above."""
    db = SessionLocal()
    try:
        create_account_for_registered_user(db, event)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def _setup_topology(channel: aio_pika.Channel) -> tuple[aio_pika.Queue, aio_pika.Exchange]:
    exchange = await channel.declare_exchange(EXCHANGE_NAME, ExchangeType.TOPIC, durable=True)

    dlx = await channel.declare_exchange(DLX_NAME, ExchangeType.FANOUT, durable=True)
    dlq = await channel.declare_queue(DLQ_NAME, durable=True)
    await dlq.bind(dlx)

    queue = await channel.declare_queue(
        QUEUE_NAME, durable=True,
        arguments={"x-dead-letter-exchange": DLX_NAME},
    )
    await queue.bind(exchange, routing_key="user.registered")
    return queue, exchange


async def _process_message(message: aio_pika.IncomingMessage, exchange: aio_pika.Exchange) -> None:
    event = json.loads(message.body)

    if event.get("event_type") != "user.registered":
        # Queue is bound only to this routing key today, but being
        # defensive here costs nothing and avoids a silent hang if this
        # queue's bindings ever get broadened later without updating this
        # handler to match.
        await message.ack()
        return

    try:
        await asyncio.to_thread(_handle_user_registered, event)
        await message.ack()
    except Exception:
        logger.exception("failed to process event %s", event.get("event_id"))
        retry_count = (message.headers or {}).get("x-retry-count", 0)
        if retry_count < MAX_RETRIES:
            await exchange.publish(
                Message(
                    body=message.body,
                    delivery_mode=DeliveryMode.PERSISTENT,
                    headers={"x-retry-count": retry_count + 1},
                    content_type="application/json",
                ),
                routing_key=message.routing_key,
            )
            await message.ack()  # original is superseded by the republish above
        else:
            logger.error("event %s exceeded max retries, routing to DLQ", event.get("event_id"))
            await message.reject(requeue=False)  # queue's DLX config routes this to the DLQ


async def run_consumer() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)
    queue, exchange = await _setup_topology(channel)

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await _process_message(message, exchange)