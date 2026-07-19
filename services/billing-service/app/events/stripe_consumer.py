import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

import aio_pika
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Invoice, OutboxEvent, Subscription

logger = logging.getLogger("billing.stripe_consumer")

EXCHANGE_NAME = "billing_events"
QUEUE_NAME = "billing-service.billing_events"
DLX_NAME = f"{QUEUE_NAME}.dlx"
DLQ_NAME = f"{QUEUE_NAME}.dlq"
MAX_RETRIES = 3


def _is_duplicate(db: Session, stripe_event_id: str) -> bool:
    inserted = db.execute(
        text("INSERT INTO billing.processed_events (stripe_event_id) VALUES (:id) ON CONFLICT DO NOTHING RETURNING stripe_event_id"),
        {"id": stripe_event_id},
    ).fetchone()
    return inserted is None


def _add_outbox(db: Session, event_type: str, payload: dict, account_id=None):
    db.add(OutboxEvent(event_type=event_type, payload=payload, account_id=account_id))


def _handle_stripe_event(raw_event: dict) -> None:
    """raw_event is the actual Stripe event object as sent by Stripe
    itself — {id, type, data: {object: {...}}, ...} — unpacked from the
    gateway's envelope['payload']['raw_event'], NOT a shape this service
    invents. See app/api/webhooks.py in api-gateway: it relays Stripe's
    object through unmodified."""
    stripe_event_id = raw_event["id"]
    stripe_event_type = raw_event["type"]
    data = raw_event["data"]["object"]

    db = SessionLocal()
    try:
        if _is_duplicate(db, stripe_event_id):
            db.commit()
            return

        if stripe_event_type == "checkout.session.completed":
            customer_id = data["customer"]
            sub = db.query(Subscription).filter(Subscription.stripe_customer_id == customer_id).first()
            if sub:
                sub.stripe_subscription_id = data.get("subscription")
                sub.status = "active"
            else:
                logger.warning(
                    "checkout.session.completed for unknown stripe customer %s (event %s)",
                    customer_id, stripe_event_id,
                )

        elif stripe_event_type == "invoice.paid":
            customer_id = data["customer"]
            sub = db.query(Subscription).filter(Subscription.stripe_customer_id == customer_id).first()
            if sub is None:
                raise ValueError(f"invoice.paid for unknown customer {customer_id}")
            sub.status = "active"
            sub.grace_period_ends_at = None

            invoice = Invoice(
                account_id=sub.account_id, stripe_invoice_id=data["id"],
                amount_cents=data["amount_paid"], status="paid",
            )
            db.add(invoice)
            _add_outbox(db, "invoice.paid", {"account_id": str(sub.account_id), "amount_cents": data["amount_paid"], "plan_tier": sub.plan_tier}, sub.account_id)

        elif stripe_event_type == "invoice.payment_failed":
            customer_id = data["customer"]
            sub = db.query(Subscription).filter(Subscription.stripe_customer_id == customer_id).first()
            if sub is None:
                raise ValueError(f"payment_failed for unknown customer {customer_id}")
            sub.status = "past_due"
            sub.grace_period_ends_at = datetime.now(timezone.utc) + timedelta(days=settings.dunning_grace_period_days)

            invoice = Invoice(
                account_id=sub.account_id, stripe_invoice_id=data["id"],
                amount_cents=data["amount_due"], status="payment_failed",
            )
            db.add(invoice)
            _add_outbox(db, "payment.failed", {"account_id": str(sub.account_id)}, sub.account_id)

        elif stripe_event_type == "customer.subscription.updated":
            sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == data["id"]).first()
            if sub:
                _add_outbox(db, "subscription.updated", {"account_id": str(sub.account_id), "status": data["status"]}, sub.account_id)

        else:
            logger.info("ignoring unhandled stripe event type %s", stripe_event_type)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def _setup_topology(channel: aio_pika.Channel):
    exchange = await channel.declare_exchange(EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True)
    dlx = await channel.declare_exchange(DLX_NAME, aio_pika.ExchangeType.FANOUT, durable=True)
    dlq = await channel.declare_queue(DLQ_NAME, durable=True)
    await dlq.bind(dlx)
    queue = await channel.declare_queue(QUEUE_NAME, durable=True, arguments={"x-dead-letter-exchange": DLX_NAME})
    # Bound to the ACTUAL routing key api-gateway publishes — confirmed
    # against services/api-gateway/app/api/webhooks.py, not assumed.
    await queue.bind(exchange, routing_key="billing.webhook_received")
    return queue, exchange


async def _process_message(message: aio_pika.IncomingMessage, exchange):
    envelope = json.loads(message.body)
    try:
        raw_event = envelope["payload"]["raw_event"]
        await asyncio.to_thread(_handle_stripe_event, raw_event)
        await message.ack()
    except Exception:
        logger.exception("failed to process stripe event %s", envelope.get("event_id"))
        retry_count = (message.headers or {}).get("x-retry-count", 0)
        if retry_count < MAX_RETRIES:
            await exchange.publish(
                aio_pika.Message(body=message.body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT, headers={"x-retry-count": retry_count + 1}),
                routing_key=message.routing_key,
            )
            await message.ack()
        else:
            await message.reject(requeue=False)


async def run_consumer():
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)
    queue, exchange = await _setup_topology(channel)
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await _process_message(message, exchange)