from app.models.generation import GenerationJob, GenerationStatus, PromptHistory


def test_generate_creates_job_and_returns_202(client, auth_headers, mock_quota_allowed):
    response = client.post("/ai/generate", json={"prompt": "write a haiku"}, headers=auth_headers())
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "running"
    assert body["model"] == "openai/gpt-4o-mini"  # default_model, since none was given
    assert body["job_id"]


def test_generate_persists_job_and_prompt_history(client, auth_headers, mock_quota_allowed, db_session):
    response = client.post("/ai/generate", json={"prompt": "write a haiku about the sea"}, headers=auth_headers(account_id="acc_1"))
    job_id = response.json()["job_id"]

    job = db_session.query(GenerationJob).filter(GenerationJob.id == job_id).one()
    assert job.account_id == "acc_1"
    assert job.status == GenerationStatus.RUNNING
    assert job.created_by_user_id == "test_user"

    history = db_session.query(PromptHistory).filter(PromptHistory.job_id == job_id).one()
    assert history.prompt == "write a haiku about the sea"
    assert history.response is None  # not filled in until PR #4


def test_generate_honors_explicit_model_choice(client, auth_headers, mock_quota_allowed):
    response = client.post(
        "/ai/generate",
        json={"prompt": "hi", "model": "anthropic/claude-3.5-sonnet"},
        headers=auth_headers(),
    )
    assert response.status_code == 202
    assert response.json()["model"] == "anthropic/claude-3.5-sonnet"


def test_generate_rejects_model_not_in_allow_list(client, auth_headers, mock_quota_allowed):
    response = client.post(
        "/ai/generate",
        json={"prompt": "hi", "model": "some/unapproved-model"},
        headers=auth_headers(),
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "invalid_model"


def test_generate_blocked_when_quota_exhausted(client, auth_headers, mock_quota_exhausted, db_session):
    response = client.post("/ai/generate", json={"prompt": "hi"}, headers=auth_headers())
    assert response.status_code == 429
    assert response.json()["detail"]["error"]["code"] == "quota_exceeded"
    # No job row should have been created -- quota check happens before any write.
    assert db_session.query(GenerationJob).count() == 0


def test_generate_requires_auth(client, mock_quota_allowed):
    response = client.post("/ai/generate", json={"prompt": "hi"})
    assert response.status_code == 401