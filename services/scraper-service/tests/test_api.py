from unittest.mock import AsyncMock

from app import job_runner


def test_create_job_requires_auth(client):
    resp = client.post("/scraper/jobs", json={"target_url": "https://example.com"})
    assert resp.status_code == 401


def test_create_job_returns_pending(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.api.jobs.execute_job", AsyncMock())
    resp = client.post("/scraper/jobs", json={"target_url": "https://example.com", "job_type": "trend_check"},
                        headers=auth_headers)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert "job_id" in body


def test_get_job_not_found(client, auth_headers):
    resp = client.get("/scraper/jobs/does-not-exist", headers=auth_headers)
    assert resp.status_code == 404


def test_get_job_returns_status(client, auth_headers, _mongo_mock):
    job_runner.scrape_jobs.insert_one({"_id": "job-x", "account_id": "acct-1", "status": "completed"})
    resp = client.get("/scraper/jobs/job-x", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_create_recurring_job(client, auth_headers):
    resp = client.post("/scraper/recurring-jobs",
                        json={"target_url": "https://example.com", "interval_seconds": 3600},
                        headers=auth_headers)
    assert resp.status_code == 201
    assert "id" in resp.json()