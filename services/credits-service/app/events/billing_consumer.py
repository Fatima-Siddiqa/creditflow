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
from app.models.ledger import CreditLedger, TransactionType

logger = logging.getLogger("billing_consumer")

SOURCE_EXCHANGE = "billing_events"
QUEUE_NAME = "credits-service.billing_events"
DLX_NAME = f"{QUEUE_NAME}.dlx"
DLQ_NAME = f"{QUEUE_NAME}.dlq"
MAX_RETRIES = 3

# Placeholder mapping of plan_tier -> credits granted on invoice.paid.
# invoice.paid's real payload (see billing-service app/api/billing.py) is
# {account_id, amount_cents, plan_tier} -- it does not carry a credit
# amount directly, so this project has to define the conversion itself.
# Revisit alongside the real pricing page copy before demo day.
PLAN_CREDIT_GRANTS = {"free": 0, "pro": 1000, "team": 5000}


def apply_invoice_paid(db: Session, event: dict) -> bool:
    """Pure business logic -- no RabbitMQ/session-lifecycle concerns, so
    tests can call this directly against a rolled-back transaction.
    Returns True if this call actually applied the credit (False if the
    event_id was already processed)."""
    event_id = event["event_id"]
    payload = event["payload"]

    inserted = db.execute(
        text(
            "INSERT INTO credits.processed_events (event_id) VALUES (:event_id) "
            "ON CONFLICT DO NOTHING RETURNING event_id"
        ),
        {"event_id": event_id},
    ).fetchone()
    if inserted is None:
        logger.info("event %s already processed, skipping", event_id)
        return False

    account_id = payload["account_id"]
    plan_tier = payload.get("plan_tier", "free")
    credits_to_add = PLAN_CREDIT_GRANTS.get(plan_tier, 0)

    db.add(
        CreditLedger(
            id=str(uuid.uuid4()),
            account_id=account_id,
            amount=credits_to_add,
            transaction_type=TransactionType.PURCHASE,
            reference_id=payload.get("stripe_invoice_id"),
        )
    )
    return True


def apply_refund_issued(db: Session, event: dict) -> bool:
    """Claws back the account's most recent PURCHASE grant. refund.issued
    doesn't carry plan_tier or a credits amount (see billing-service
    app/api/billing.py), so there's no exact invoice-to-grant link
    available yet -- undoing the latest purchase is a documented
    simplification, not a guarantee of matching the refunded invoice."""
    event_id = event["event_id"]
    payload = event["payload"]

    inserted = db.execute(
        text(
            "INSERT INTO credits.processed_events (event_id) VALUES (:event_id) "
            "ON CONFLICT DO NOTHING RETURNING event_id"
        ),
        {"event_id": event_id},
    ).fetchone()
    if inserted is None:
        logger.info("event %s already processed, skipping", event_id)
        return False

    account_id = payload["account_id"]
    last_purchase = (
        db.query(CreditLedger)
        .filter(CreditLedger.account_id == account_id, CreditLedger.transaction_type == TransactionType.PURCHASE)
        .order_by(CreditLedger.created_at.desc())
        .first()
    )
    clawback_amount = last_purchase.amount if last_purchase else 0

    db.add(
        CreditLedger(
            id=str(uuid.uuid4()),
            account_id=account_id,
            amount=-clawback_amount,
            transaction_type=TransactionType.REFUND_CLAWBACK,
            reference_id=payload.get("stripe_refund_id"),
        )
    )
    return True


HANDLERS = {"invoice.paid": apply_invoice_paid, "refund.issued": apply_refund_issued}


def _handle_event(event: dict) -> tuple[bool, str | None]:
    """Runs in a worker thread via asyncio.to_thread -- sync SQLAlchemy,
    matching every other service. Owns its own session/commit/rollback."""
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

    queue = await channel.declare_queue(
        QUEUE_NAME, durable=True,
        arguments={"x-dead-letter-exchange": DLX_NAME},
    )
    await queue.bind(exchange, routing_key="invoice.paid")
    await queue.bind(exchange, routing_key="refund.issued")
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
                Message(
                    body=message.body,
                    delivery_mode=DeliveryMode.PERSISTENT,
                    headers={"x-retry-count": retry_count + 1},
                    content_type="application/json",
                ),
                routing_key=message.routing_key,
            )
            await message.ack()
        else:
            logger.error("event %s exceeded max retries, routing to DLQ", event.get("event_id"))
            await message.reject(requeue=False)
        return

    if applied and event["event_type"] == "invoice.paid":
        try:
            credits_amount = PLAN_CREDIT_GRANTS.get(event["payload"].get("plan_tier", "free"), 0)
            await publish_event("credits.credited", {"account_id": account_id, "amount": credits_amount}, account_id=account_id)
        except Exception:
            logger.exception("credited account %s but failed to publish credits.credited", account_id)
    elif applied and event["event_type"] == "refund.issued":
        try:
            await publish_event("credits.debited", {"account_id": account_id, "reason": "refund"}, account_id=account_id)
        except Exception:
            logger.exception("debited account %s but failed to publish credits.debited", account_id)


async def run_consumer() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)
    queue, exchange = await _setup_topology(channel)

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await _process_message(message, exchange)