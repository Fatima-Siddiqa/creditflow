import asyncio
import json
import logging

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.events.publisher import publish_event
from app.models.usage import UsageLedger
from app.period import get_current_period, seconds_until_period_end
from app.usage_redis import usage_redis_client

logger = logging.getLogger("ai_consumer")

SOURCE_EXCHANGE = "ai_events"
QUEUE_NAME = "usage-service.ai_events"
DLX_NAME = f"{QUEUE_NAME}.dlx"
DLQ_NAME = f"{QUEUE_NAME}.dlq"
MAX_RETRIES = 3

THRESHOLDS = (80, 100)


def _usage_key(account_id: str, period: str) -> str:
    return f"usage:{account_id}:{period}"


def _check_and_mark_thresholds(db: Session, account_id: str, period: str, used: int, quota: int) -> list[int]:
    """Fires each threshold at most once per (account_id, period) --
    existence of a row in usage_threshold_notifications IS the 'already
    notified' flag (Phase 7 plan: 'track already notified state to avoid
    spamming'). ON CONFLICT DO NOTHING against the table's unique
    constraint makes this race-safe without a separate lock."""
    if quota <= 0:
        return []
    pct = (used / quota) * 100
    crossed: list[int] = []
    for threshold in THRESHOLDS:
        if pct < threshold:
            continue
        inserted = db.execute(
            text(
                "INSERT INTO usage.usage_threshold_notifications (account_id, period, threshold) "
                "VALUES (:account_id, :period, :threshold) ON CONFLICT DO NOTHING RETURNING id"
            ),
            {"account_id": account_id, "period": period, "threshold": threshold},
        ).fetchone()
        if inserted is not None:
            crossed.append(threshold)
    return crossed


def apply_generation_completed(db: Session, redis_client, event: dict) -> tuple[bool, list[dict]]:
    """Pure business logic -- no RabbitMQ/session-lifecycle concerns, same
    shape as credits-service's apply_invoice_paid, so tests can call it
    directly against a rolled-back transaction + a real (test-DB-index)
    Redis client. Returns (applied, threshold_events); threshold_events is
    what the caller should publish AFTER commit, one usage.threshold_reached
    per newly-crossed threshold.

    Payload shape ({account_id, model, tokens_used, cost_cents}) is this
    project's own DOCUMENTED ASSUMPTION about what ai-generation-service
    (Phase 8, not built yet) will publish, following the same pattern
    docs/EVENT_CONTRACTS.md already used for invoice.paid before
    billing-service existed. Update this function (not the other way
    around) once Phase 8 is real -- see docs/EVENT_CONTRACTS.md's own
    instruction for this situation.
    """
    event_id = event["event_id"]
    payload = event["payload"]

    inserted = db.execute(
        text(
            "INSERT INTO usage.processed_events (event_id) VALUES (:event_id) "
            "ON CONFLICT DO NOTHING RETURNING event_id"
        ),
        {"event_id": event_id},
    ).fetchone()
    if inserted is None:
        logger.info("event %s already processed, skipping", event_id)
        return False, []

    account_id = payload["account_id"]
    model = payload["model"]
    tokens_used = int(payload["tokens_used"])
    cost_cents = int(payload.get("cost_cents", 0))

    db.add(UsageLedger(account_id=account_id, model=model, tokens_used=tokens_used, cost_cents=cost_cents))

    period = get_current_period()
    key = _usage_key(account_id, period)
    new_total = redis_client.incrby(key, tokens_used)
    if redis_client.ttl(key) < 0:
        redis_client.expire(key, seconds_until_period_end(period))

    crossed = _check_and_mark_thresholds(db, account_id, period, new_total, settings.default_monthly_token_quota)
    threshold_events = [{"account_id": account_id, "threshold": t, "period": period} for t in crossed]
    return True, threshold_events


def _handle_event(event: dict) -> tuple[bool, list[dict]]:
    """Runs in a worker thread via asyncio.to_thread -- sync SQLAlchemy,
    matching every other service. Owns its own session/commit/rollback."""
    db = SessionLocal()
    try:
        applied, threshold_events = apply_generation_completed(db, usage_redis_client, event)
        db.commit()
        return applied, threshold_events
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
    await queue.bind(exchange, routing_key="ai.generation_completed")
    return queue, exchange


async def _process_message(message: aio_pika.IncomingMessage, exchange: aio_pika.Exchange) -> None:
    event = json.loads(message.body)

    if event.get("event_type") != "ai.generation_completed":
        await message.ack()
        return

    try:
        applied, threshold_events = await asyncio.to_thread(_handle_event, event)
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

    if applied:
        for te in threshold_events:
            try:
                await publish_event(
                    "usage.threshold_reached",
                    {"account_id": te["account_id"], "threshold": te["threshold"], "period": te["period"]},
                    account_id=te["account_id"],
                )
            except Exception:
                logger.exception(
                    "recorded usage for account %s but failed to publish usage.threshold_reached", te["account_id"]
                )


async def run_consumer() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)
    queue, exchange = await _setup_topology(channel)

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await _process_message(message, exchange)
