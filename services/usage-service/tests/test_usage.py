import uuid

from app.config import settings
from app.events.ai_consumer import apply_generation_completed
from app.models.usage import UsageLedger
from app.period import get_current_period
from app.reconciliation import reconcile_account


def _generation_completed_event(account_id, model="fast-model", tokens_used=1000, cost_cents=10, event_id=None):
    return {
        "event_id": str(event_id or uuid.uuid4()),
        "event_type": "ai.generation_completed",
        "account_id": account_id,
        "producer": "ai-generation-service",
        "schema_version": 1,
        "payload": {"account_id": account_id, "model": model, "tokens_used": tokens_used, "cost_cents": cost_cents},
    }


def _usage_key(account_id, period):
    return f"usage:{account_id}:{period}"


# --- GET /usage/check ---------------------------------------------------

def test_check_quota_allowed_when_under_limit(client, auth_headers):
    headers = auth_headers(account_id="acc_fresh")
    response = client.get("/usage/check", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["used"] == 0
    assert body["allowed"] is True
    assert body["remaining"] == settings.default_monthly_token_quota


def test_check_quota_blocks_once_over_limit(client, auth_headers, test_usage_redis_client):
    account_id = "acc_over_quota"
    period = get_current_period()
    test_usage_redis_client.set(_usage_key(account_id, period), settings.default_monthly_token_quota + 1)

    headers = auth_headers(account_id=account_id)
    response = client.get("/usage/check", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["remaining"] == 0


def test_check_quota_requires_auth(client):
    response = client.get("/usage/check")
    assert response.status_code == 401


# --- apply_generation_completed (consumer business logic) --------------

def test_generation_completed_records_ledger_and_increments_counter(db_session, test_usage_redis_client):
    account_id = "acc_gen_1"
    event = _generation_completed_event(account_id, tokens_used=500)

    applied, threshold_events = apply_generation_completed(db_session, test_usage_redis_client, event)
    db_session.flush()

    assert applied is True
    assert threshold_events == []
    entry = db_session.query(UsageLedger).filter(UsageLedger.account_id == account_id).one()
    assert entry.tokens_used == 500

    period = get_current_period()
    assert int(test_usage_redis_client.get(_usage_key(account_id, period))) == 500


def test_duplicate_generation_completed_does_not_double_count(db_session, test_usage_redis_client):
    account_id = "acc_gen_dup"
    event = _generation_completed_event(account_id, tokens_used=200, event_id=uuid.uuid4())

    first_applied, _ = apply_generation_completed(db_session, test_usage_redis_client, event)
    db_session.flush()
    second_applied, _ = apply_generation_completed(db_session, test_usage_redis_client, event)  # redelivery
    db_session.flush()

    assert first_applied is True
    assert second_applied is False
    entries = db_session.query(UsageLedger).filter(UsageLedger.account_id == account_id).all()
    assert len(entries) == 1

    period = get_current_period()
    assert int(test_usage_redis_client.get(_usage_key(account_id, period))) == 200


def test_threshold_reached_fires_once_at_80_and_once_at_100(db_session, test_usage_redis_client):
    account_id = "acc_threshold"
    quota = settings.default_monthly_token_quota

    # Cross 80% only.
    e1 = _generation_completed_event(account_id, tokens_used=int(quota * 0.85))
    applied1, thresholds1 = apply_generation_completed(db_session, test_usage_redis_client, e1)
    db_session.flush()
    assert applied1 is True
    assert [t["threshold"] for t in thresholds1] == [80]

    # Redelivery-safe: another chunk that keeps us under 100% shouldn't re-fire 80.
    e2 = _generation_completed_event(account_id, tokens_used=int(quota * 0.05))
    applied2, thresholds2 = apply_generation_completed(db_session, test_usage_redis_client, e2)
    db_session.flush()
    assert applied2 is True
    assert thresholds2 == []

    # Now cross 100% -- only 100 should fire, not 80 again.
    e3 = _generation_completed_event(account_id, tokens_used=int(quota * 0.20))
    applied3, thresholds3 = apply_generation_completed(db_session, test_usage_redis_client, e3)
    db_session.flush()
    assert applied3 is True
    assert [t["threshold"] for t in thresholds3] == [100]


# --- reconciliation -------------------------------------------------------

def test_reconciliation_self_heals_a_corrupted_counter(db_session, test_usage_redis_client):
    account_id = "acc_corrupted"
    period = get_current_period()

    # Two real ledger writes totalling 700 tokens.
    apply_generation_completed(db_session, test_usage_redis_client, _generation_completed_event(account_id, tokens_used=300))
    db_session.flush()
    apply_generation_completed(db_session, test_usage_redis_client, _generation_completed_event(account_id, tokens_used=400))
    db_session.flush()

    # Deliberately corrupt the fast-path counter.
    test_usage_redis_client.set(_usage_key(account_id, period), 999999)
    assert int(test_usage_redis_client.get(_usage_key(account_id, period))) == 999999

    corrected = reconcile_account(db_session, test_usage_redis_client, account_id, period)

    assert corrected == 700
    assert int(test_usage_redis_client.get(_usage_key(account_id, period))) == 700


# --- GET /usage/summary ----------------------------------------------------

def test_summary_reflects_ledger_by_model(client, auth_headers, db_session, test_usage_redis_client):
    account_id = "acc_summary"
    apply_generation_completed(db_session, test_usage_redis_client, _generation_completed_event(account_id, model="fast", tokens_used=100, cost_cents=5))
    apply_generation_completed(db_session, test_usage_redis_client, _generation_completed_event(account_id, model="quality", tokens_used=50, cost_cents=20))
    db_session.commit()

    headers = auth_headers(account_id=account_id)
    response = client.get("/usage/summary", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_tokens"] == 150
    assert body["total_cost_cents"] == 25
    assert {m["model"] for m in body["by_model"]} == {"fast", "quality"}


def test_summary_rejects_cross_account_read_without_internal_secret(client, auth_headers):
    headers = auth_headers(account_id="acc_self")
    response = client.get("/usage/summary", params={"account_id": "acc_someone_else"}, headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"]["error"]["code"] == "forbidden"


def test_summary_allows_cross_account_read_with_internal_secret(client, auth_headers, db_session, test_usage_redis_client):
    other_account = "acc_admin_target"
    apply_generation_completed(db_session, test_usage_redis_client, _generation_completed_event(other_account, tokens_used=42))
    db_session.commit()

    headers = auth_headers(account_id="acc_self")
    headers["X-Internal-Secret"] = settings.internal_service_secret
    response = client.get("/usage/summary", params={"account_id": other_account}, headers=headers)
    assert response.status_code == 200
    assert response.json()["account_id"] == other_account
    assert response.json()["total_tokens"] == 42
