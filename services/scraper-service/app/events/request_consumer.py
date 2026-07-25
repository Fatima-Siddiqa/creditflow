import json
import logging
import uuid

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from app.config import settings
from app.db import scrape_jobs
from app.job_runner import execute_job

logger = logging.getLogger("request_consumer")

EXCHANGE_NAME = "scraper_events"
QUEUE_NAME = "scraper-service.scrape_requested"
DLX_NAME = f"{QUEUE_NAME}.dlx"
DLQ_NAME = f"{QUEUE_NAME}.dlq"
MAX_RETRIES = 3


def _already_processed(event_id: str) -> bool:
    """Idempotency guard: scrape jobs aren't strictly destructive to
    re-run, but re-processing the same delivery would still duplicate
    scraped_documents entries and double-publish scrape.completed."""
    result = scrape_jobs.update_one(
        {"_id": f"event:{event_id}"},
        {"$setOnInsert": {"_id": f"event:{event_id}", "status": "processed_marker"}},
        upsert=True,
    )
    return result.upserted_id is None


async def _setup_topology(channel: aio_pika.Channel) -> tuple[aio_pika.Queue, aio_pika.Exchange]:
    exchange = await channel.declare_exchange(EXCHANGE_NAME, ExchangeType.TOPIC, durable=True)
    dlx = await channel.declare_exchange(DLX_NAME, ExchangeType.FANOUT, durable=True)
    dlq = await channel.declare_queue(DLQ_NAME, durable=True)
    await dlq.bind(dlx)
    queue = await channel.declare_queue(QUEUE_NAME, durable=True, arguments={"x-dead-letter-exchange": DLX_NAME})
    await queue.bind(exchange, routing_key="scrape.requested")
    return queue, exchange


async def _process_message(message: aio_pika.IncomingMessage, exchange: aio_pika.Exchange) -> None:
    event = json.loads(message.body)
    if event.get("event_type") != "scrape.requested":
        await message.ack()
        return

    if _already_processed(event["event_id"]):
        logger.info("event %s already processed, skipping", event["event_id"])
        await message.ack()
        return

    payload = event["payload"]
    job_id = payload.get("job_id") or str(uuid.uuid4())
    try:
        scrape_jobs.insert_one({"_id": job_id, "account_id": payload.get("account_id"),
                                 "target_url": payload["target_url"], "job_type": payload.get("job_type", "generic"),
                                 "status": "pending", "source": "event"})
        await execute_job(job_id, payload.get("account_id"), payload["target_url"], payload.get("job_type", "generic"))
        await message.ack()
    except Exception:
        logger.exception("failed to process scrape.requested %s", event.get("event_id"))
        retry_count = (message.headers or {}).get("x-retry-count", 0)
        if retry_count < MAX_RETRIES:
            retry_event = dict(event)
            retry_event["event_id"] = str(uuid.uuid4())
            await exchange.publish(
                Message(body=json.dumps(retry_event).encode(), delivery_mode=DeliveryMode.PERSISTENT,
                        headers={"x-retry-count": retry_count + 1}, content_type="application/json"),
                routing_key=message.routing_key,
            )
            await message.ack()
        else:
            await message.reject(requeue=False)


async def run_consumer() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)
    queue, exchange = await _setup_topology(channel)
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await _process_message(message, exchange)