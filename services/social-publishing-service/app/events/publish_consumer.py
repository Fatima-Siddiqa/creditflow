import asyncio
import json
import logging
import uuid

import aio_pika
import httpx
from aio_pika import DeliveryMode, ExchangeType, Message
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.crypto import decrypt
from app.db import SessionLocal
from app.events.publisher import publish_event
from app.linkedin_client import register_upload, upload_binary, publish_ugc_post
from app.models.social import PublishJob, PublishStatus, PostMedia, SocialConnection

logger = logging.getLogger("publish_consumer")

SOURCE_EXCHANGE = "content_events"
QUEUE_NAME = "social-publishing-service.content_events"
DLX_NAME = f"{QUEUE_NAME}.dlx"
DLQ_NAME = f"{QUEUE_NAME}.dlq"
MAX_RETRIES = 3


def _mark_processed(db: Session, event_id: str) -> bool:
    """Returns False if this event_id was already processed (idempotent
    redelivery -- critical here, we do not want to double-post to
    LinkedIn)."""
    inserted = db.execute(
        text("INSERT INTO social.processed_events (event_id) VALUES (:event_id) ON CONFLICT DO NOTHING RETURNING event_id"),
        {"event_id": event_id},
    ).fetchone()
    return inserted is not None


async def apply_content_scheduled(db: Session, event: dict) -> bool:
    payload = event["payload"]
    account_id, content_id, schedule_id = payload["account_id"], payload["content_id"], payload["schedule_id"]

    conn = db.query(SocialConnection).filter(SocialConnection.account_id == account_id).one_or_none()
    if conn is None:
        return False

    job = db.query(PublishJob).filter(PublishJob.scheduled_post_id == schedule_id).one_or_none()
    if job is None:
        job = PublishJob(id=str(uuid.uuid4()), scheduled_post_id=schedule_id, content_id=content_id,
                          account_id=account_id, status=PublishStatus.PUBLISHING, attempt_count=0)
        db.add(job)
    db.commit()  # job row survives even if the LinkedIn calls below fail

    async with httpx.AsyncClient() as client:
        content_resp = await client.get(f"{settings.content_service_url}/content/{content_id}/internal",
                                          headers={"X-Internal-Secret": settings.internal_service_secret})
        content_resp.raise_for_status()
        content = content_resp.json()

    access_token = decrypt(conn.access_token_enc)
    asset_urn = None
    if content.get("image_url"):
        # content["image_url"] is a path relative to content-service's
        # own root (e.g. "/uploads/{content_id}/{filename}"), not a
        # fully-qualified URL -- httpx.get() on the bare path fails
        # outright (no scheme/host). Build the real internal URL the
        # same way the /internal call above already does.
        image_url = f"{settings.content_service_url}{content['image_url']}"
        async with httpx.AsyncClient() as client:
            image_resp = await client.get(image_url)
            image_resp.raise_for_status()
            image_bytes = image_resp.content
        upload_url, asset_urn = await register_upload(access_token, conn.linkedin_member_urn)
        await upload_binary(upload_url, access_token, image_bytes)
        db.add(PostMedia(id=str(uuid.uuid4()), publish_job_id=job.id, linkedin_asset_urn=asset_urn, image_url=content["image_url"]))

    post_urn = await publish_ugc_post(access_token, conn.linkedin_member_urn, content["body"], asset_urn)
    job.status = PublishStatus.PUBLISHED
    job.linkedin_post_urn = post_urn
    db.commit()
    return True


HANDLERS = {"content.scheduled": apply_content_scheduled}


async def _handle_event(event: dict) -> tuple[bool, str | None]:
    """Async (unlike content-service's ai_consumer._handle_event) --
    this handler makes real httpx/LinkedIn calls, so it can't be run
    through asyncio.to_thread the way a pure-sync-DB handler can."""
    handler = HANDLERS.get(event.get("event_type"))
    if handler is None:
        return False, None

    db = SessionLocal()
    try:
        if not _mark_processed(db, event["event_id"]):
            logger.info("event %s already processed, skipping", event["event_id"])
            db.commit()
            return False, event["payload"]["account_id"]
        applied = await handler(db, event)
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
    await queue.bind(exchange, routing_key="content.scheduled")
    return queue, exchange


async def _process_message(message: aio_pika.IncomingMessage, exchange: aio_pika.Exchange) -> None:
    event = json.loads(message.body)
    if event.get("event_type") not in HANDLERS:
        await message.ack()
        return

    try:
        applied, account_id = await _handle_event(event)
        await message.ack()
    except Exception as exc:
        logger.exception("failed to process event %s", event.get("event_id"))
        retry_count = (message.headers or {}).get("x-retry-count", 0)
        db = SessionLocal()
        try:
            job = db.query(PublishJob).filter(PublishJob.scheduled_post_id == event["payload"]["schedule_id"]).one_or_none()
            if job is not None:
                job.attempt_count += 1
                if retry_count >= MAX_RETRIES:
                    job.status = PublishStatus.FAILED
                    job.last_error = str(exc)[:1000]
                db.commit()
        finally:
            db.close()

        if retry_count < MAX_RETRIES:
            await exchange.publish(
                Message(body=message.body, delivery_mode=DeliveryMode.PERSISTENT,
                        headers={"x-retry-count": retry_count + 1}, content_type="application/json"),
                routing_key=message.routing_key,
            )
            await message.ack()
        else:
            logger.error("event %s exceeded max retries, routing to DLQ", event.get("event_id"))
            await publish_event("post.failed", {"account_id": event["payload"]["account_id"], "content_id": event["payload"]["content_id"], "reason": "max retries exceeded"}, account_id=event["payload"]["account_id"])
            await message.reject(requeue=False)
        return

    if applied:
        try:
            await publish_event("post.published", {"account_id": account_id}, account_id=account_id)
        except Exception:
            logger.exception("published to LinkedIn for account %s but failed to publish post.published", account_id)


async def run_consumer() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)
    queue, exchange = await _setup_topology(channel)
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await _process_message(message, exchange)