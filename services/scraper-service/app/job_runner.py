import logging
import uuid
from datetime import datetime, timezone

from app.db import scrape_jobs, scraped_documents
from app.events.publisher import publish_event
from app.scraper import run_scrape, ScrapeBlocked, ScrapeFailed

logger = logging.getLogger("job_runner")


async def execute_job(job_id: str, account_id: str | None, target_url: str, job_type: str) -> None:
    """Runs one scrape job to completion, persists status + result, and
    emits scrape.completed / scrape.failed. Shared by the REST endpoint's
    background task and the scrape.requested consumer -- so a job triggered
    either way behaves identically and never gets stuck in 'running'."""
    scrape_jobs.update_one({"_id": job_id}, {"$set": {"status": "completed", "document_id": doc_id, "data": data}})
    try:
        data = await run_scrape(target_url, job_type)
    except ScrapeBlocked as exc:
        scrape_jobs.update_one({"_id": job_id}, {"$set": {"status": "failed", "error": str(exc)}})
        await publish_event("scrape.failed", {"job_id": job_id, "account_id": account_id, "reason": str(exc)}, account_id=account_id)
        return
    except ScrapeFailed as exc:
        scrape_jobs.update_one({"_id": job_id}, {"$set": {"status": "failed", "error": str(exc)}})
        await publish_event("scrape.failed", {"job_id": job_id, "account_id": account_id, "reason": str(exc)}, account_id=account_id)
        return
    except Exception as exc:
        logger.exception("unexpected scrape failure for job %s", job_id)
        scrape_jobs.update_one({"_id": job_id}, {"$set": {"status": "failed", "error": str(exc)}})
        await publish_event("scrape.failed", {"job_id": job_id, "account_id": account_id, "reason": "internal_error"}, account_id=account_id)
        return

    doc_id = str(uuid.uuid4())
    scraped_documents.insert_one({
        "_id": doc_id,
        "job_id": job_id,
        "account_id": account_id,
        "target_url": target_url,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    })
    scrape_jobs.update_one({"_id": job_id}, {"$set": {"status": "completed", "document_id": doc_id}})
    await publish_event("scrape.completed", {"job_id": job_id, "account_id": account_id, "document_id": doc_id}, account_id=account_id)