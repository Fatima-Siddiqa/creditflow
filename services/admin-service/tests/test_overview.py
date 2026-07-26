from app.schemas import AccountOverview


def test_superadmin_can_view_any_account_overview(client, auth_headers, monkeypatch):
    """Overview aggregation correctly combines data from 3 separate
    service calls — mocks those calls, asserts the merge logic
    (per PHASE_14's test checklist)."""

    async def fake_profile(account_id):
        return {"plan_tier": "pro", "seat_count": 4}

    async def fake_balance(account_id):
        return {"balance": 1500}

    async def fake_usage(account_id):
        return {"total_tokens": 98000, "total_cost_cents": 420}

    monkeypatch.setattr("app.api.admin.get_account_profile", fake_profile)
    monkeypatch.setattr("app.api.admin.get_credit_balance", fake_balance)
    monkeypatch.setattr("app.api.admin.get_usage_summary", fake_usage)

    headers = auth_headers(platform_role="superadmin")
    resp = client.get("/admin/accounts/some-account-id/overview", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "account_id": "some-account-id",
        "plan_tier": "pro",
        "seat_count": 4,
        "credit_balance": 1500,
        "usage_tokens_this_period": 98000,
        "usage_cost_cents_this_period": 420,
    }


def test_tenant_admin_can_view_own_account_overview(client, auth_headers, monkeypatch):
    async def fake_profile(account_id):
        return {"plan_tier": "free", "seat_count": 1}

    async def fake_balance(account_id):
        return {"balance": 0}

    async def fake_usage(account_id):
        return {"total_tokens": 0, "total_cost_cents": 0}

    monkeypatch.setattr("app.api.admin.get_account_profile", fake_profile)
    monkeypatch.setattr("app.api.admin.get_credit_balance", fake_balance)
    monkeypatch.setattr("app.api.admin.get_usage_summary", fake_usage)

    headers = auth_headers(account_id="acc-1", role="owner")
    resp = client.get("/admin/accounts/acc-1/overview", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["account_id"] == "acc-1"


def test_tenant_admin_cannot_view_other_account_overview(client, auth_headers, monkeypatch):
    # No client mocks needed — require_admin_access rejects before any
    # of the three service calls would happen.
    monkeypatch.setattr("app.api.admin.get_account_profile", lambda account_id: (_ for _ in ()).throw(AssertionError("should not be called")))

    headers = auth_headers(account_id="acc-1", role="owner")
    resp = client.get("/admin/accounts/acc-2/overview", headers=headers)

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "insufficient_role"


def test_member_role_cannot_view_own_account_overview(client, auth_headers):
    """Only owner/admin qualify as TenantAdmin per PHASE_14's RBAC nuance
    — a plain member is neither SuperAdmin nor TenantAdmin."""
    headers = auth_headers(account_id="acc-1", role="member")
    resp = client.get("/admin/accounts/acc-1/overview", headers=headers)

    assert resp.status_code == 403