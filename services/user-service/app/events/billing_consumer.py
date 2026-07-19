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
from app.models import Account

logger = logging.getLogger("billing_consumer")

EXCHANGE_NAME = "billing_events"
QUEUE_NAME = "user-service.billing_events"
DLX_NAME = f"{QUEUE_NAME}.dlx"
DLQ_NAME = f"{QUEUE_NAME}.dlq"
MAX_RETRIES = 3


def apply_invoice_paid(db: Session, event: dict) -> bool:
    """Pure business logic, no RabbitMQ or session-lifecycle concerns —
    mirrors app/events/identity_consumer.py's
    create_account_for_registered_user exactly, same idempotency pattern
    from Phase 1, same processed_events table (shared safely across both
    consumers: event_id is a globally-unique UUID assigned by whichever
    service produced it, so there's no collision risk between an
    identity_events event_id and a billing_events one).

    Per Phase 4's file: 'may adjust plan_tier/seat count'. Deliberately
    does NOT touch seat count — accounts.seat_count isn't a stored column
    (see AccountResponse in app/api/accounts.py, it's a live COUNT(*) over
    account_members), so there's nothing to write for it here. If a future
    phase wants plan-tier-based seat LIMITS enforced, that's a new column
    and a new decision, not something implied by what's written down so
    far — noting this now so it isn't silently assumed later.

    Payload shape (account_id, plan_tier, amount) per Phase 5's own
    handoff note to Phase 6 — Billing Service doesn't exist yet, so this
    is this project's documented assumption about what it will publish,
    not a contract confirmed against real code. See
    docs/EVENT_CONTRACTS.md for where this is written down for whoever
    builds Phase 5 next. `amount` isn't read here; Credits Service (Phase
    6) is the one that cares about it.
    """
    event_id = uuid.UUID(event["event_id"])
    account_id = uuid.UUID(event["payload"]["account_id"])
    plan_tier = event["payload"]["plan_tier"]

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

    account = db.query(Account).filter(Account.id == account_id).first()
    if account is None:
        # Raising rolls back the WHOLE transaction, including the
        # processed_events insert above — so this is retried (then DLQ'd
        # after MAX_RETRIES) rather than silently marked "handled" for an
        # update that never actually happened. A missing account here
        # means something upstream is wrong; it should surface, not
        # vanish.
        raise ValueError(f"invoice.paid for unknown account {account_id}")

    account.plan_tier = plan_tier
    return True


def _handle_invoice_paid(event: dict) -> None:
    """Runs in a worker thread (see asyncio.to_thread in _process_message)
    — same reasoning as identity_consumer.py's _handle_user_registered."""
    db = SessionLocal()
    try:
        apply_invoice_paid(db, event)
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
    await queue.bind(exchange, routing_key="invoice.paid")
    return queue, exchange


async def _process_message(message: aio_pika.IncomingMessage, exchange: aio_pika.Exchange) -> None:
    event = json.loads(message.body)

    if event.get("event_type") != "invoice.paid":
        await message.ack()
        return

    try:
        await asyncio.to_thread(_handle_invoice_paid, event)
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