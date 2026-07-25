from unittest.mock import AsyncMock

import pytest

from app import job_runner
from app.scraper import ScrapeFailed


async def test_successful_scrape_produces_one_document_and_completed_event(monkeypatch, _mongo_mock):
    async def fake_run_scrape(url, job_type):
        return {"title": "Example", "text_excerpt": "hello world"}

    monkeypatch.setattr(job_runner, "run_scrape", fake_run_scrape)
    publish_mock = AsyncMock()
    monkeypatch.setattr(job_runner, "publish_event", publish_mock)

    job_runner.scrape_jobs.insert_one({"_id": "job-1", "account_id": "acct-1", "status": "pending"})

    await job_runner.execute_job("job-1", "acct-1", "https://example.com", "trend_check")

    docs = list(job_runner.scraped_documents.find({"job_id": "job-1"}))
    assert len(docs) == 1
    assert docs[0]["account_id"] == "acct-1"

    job = job_runner.scrape_jobs.find_one({"_id": "job-1"})
    assert job["status"] == "completed"

    publish_mock.assert_awaited_once()
    args, kwargs = publish_mock.await_args
    assert args[0] == "scrape.completed"


async def test_failed_scrape_emits_failed_event_and_marks_job_failed(monkeypatch, _mongo_mock):
    async def fake_run_scrape(url, job_type):
        raise ScrapeFailed("target unreachable")

    monkeypatch.setattr(job_runner, "run_scrape", fake_run_scrape)
    publish_mock = AsyncMock()
    monkeypatch.setattr(job_runner, "publish_event", publish_mock)

    job_runner.scrape_jobs.insert_one({"_id": "job-2", "account_id": "acct-1", "status": "pending"})

    await job_runner.execute_job("job-2", "acct-1", "https://unreachable.example", "trend_check")

    job = job_runner.scrape_jobs.find_one({"_id": "job-2"})
    assert job["status"] == "failed"
    assert "unreachable" in job["error"]

    docs = list(job_runner.scraped_documents.find({"job_id": "job-2"}))
    assert len(docs) == 0

    publish_mock.assert_awaited_once()
    args, kwargs = publish_mock.await_args
    assert args[0] == "scrape.failed"