import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from app.db import scrape_jobs, recurring_jobs
from app.dependencies import get_current_payload
from app.job_runner import execute_job

router = APIRouter()


class ScrapeJobRequest(BaseModel):
    target_url: str
    job_type: str = "generic"


class RecurringJobRequest(BaseModel):
    target_url: str
    job_type: str = "recurring"
    interval_seconds: int = 86400


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_job(body: ScrapeJobRequest, background_tasks: BackgroundTasks, payload: dict = Depends(get_current_payload)):
    account_id = payload["account_id"]
    job_id = str(uuid.uuid4())
    scrape_jobs.insert_one({"_id": job_id, "account_id": account_id, "target_url": body.target_url,
                             "job_type": body.job_type, "status": "pending", "source": "rest"})
    background_tasks.add_task(execute_job, job_id, account_id, body.target_url, body.job_type)
    return {"job_id": job_id, "status": "pending"}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, payload: dict = Depends(get_current_payload)):
    job = scrape_jobs.find_one({"_id": job_id})
    if job is None or job.get("account_id") != payload["account_id"]:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Job not found.", "details": {}}})
    job["id"] = job.pop("_id")
    return job


@router.post("/recurring-jobs", status_code=status.HTTP_201_CREATED)
def create_recurring_job(body: RecurringJobRequest, payload: dict = Depends(get_current_payload)):
    from datetime import datetime, timezone
    account_id = payload["account_id"]
    job_id = str(uuid.uuid4())
    recurring_jobs.insert_one({"_id": job_id, "account_id": account_id, "target_url": body.target_url,
                                "job_type": body.job_type, "interval_seconds": body.interval_seconds,
                                "active": True, "next_run_at": datetime.now(timezone.utc).isoformat()})
    return {"id": job_id}