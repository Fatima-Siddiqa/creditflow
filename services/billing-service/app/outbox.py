import asyncio
import json
import logging

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal

logger = logging.getLogger("billing.outbox")
EXCHANGE_NAME = "billing_events"


async def run_outbox_poller():
    while True:
        try:
            db = SessionLocal()
            try:
                rows = db.execute(
                    text("""SELECT id, event_type, payload, account_id FROM billing.outbox_events
                             WHERE published = false ORDER BY created_at LIMIT 50 FOR UPDATE SKIP LOCKED""")
                ).fetchall()

                if rows:
                    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
                    try:
                        channel = await connection.channel(publisher_confirms=True)
                        exchange = await channel.declare_exchange(EXCHANGE_NAME, ExchangeType.TOPIC, durable=True)
                        for row in rows:
                            envelope = {
                                "event_id": str(row.id),
                                "event_type": row.event_type,
                                "account_id": str(row.account_id) if row.account_id else None,
                                "producer": "billing-service",
                                "schema_version": 1,
                                "payload": row.payload,
                            }
                            message = Message(
                                body=json.dumps(envelope).encode(),
                                delivery_mode=DeliveryMode.PERSISTENT,
                                content_type="application/json",
                            )
                            confirm = await exchange.publish(message, routing_key=row.event_type)
                            if confirm:
                                db.execute(text("UPDATE billing.outbox_events SET published = true WHERE id = :id"), {"id": row.id})
                            else:
                                logger.warning("publish not confirmed for outbox row %s", row.id)
                        db.commit()
                    finally:
                        await connection.close()
            finally:
                db.close()
        except Exception:
            logger.exception("outbox poller cycle failed, will retry")
        await asyncio.sleep(settings.outbox_poll_interval_seconds)