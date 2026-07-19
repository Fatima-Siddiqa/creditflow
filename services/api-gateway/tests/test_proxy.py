import httpx

from app.config import settings


def test_unknown_prefix_returns_404(client):
    # No token needed — an unregistered prefix 404s before the auth gate
    # even runs, so this is unaffected by JWT verification.
    resp = client.get("/api/nonexistent/ping")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "route_not_found"


def _authed_headers(make_token, test_redis_client, jti="proxy-test-jti"):
    token = make_token(jti=jti)
    test_redis_client.setex(f"jti:{jti}", 900, "1")
    return {"Authorization": f"Bearer {token}"}


def test_known_prefix_forwards_to_correct_service_url(client, monkeypatch, make_token, test_redis_client):
    captured = {}

    async def _fake_forward(method, url, params, content, headers):
        captured["method"] = method
        captured["url"] = url
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    headers = _authed_headers(make_token, test_redis_client)
    resp = client.get("/api/auth/me", headers=headers)

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert captured["method"] == "GET"
    assert captured["url"] == f"{settings.auth_service_url}/auth/me"


def test_downstream_connection_error_returns_502(client, monkeypatch, make_token, test_redis_client):
    async def _fake_forward(method, url, params, content, headers):
        raise httpx.ConnectError("simulated: service not built yet", request=httpx.Request(method, url))

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    headers = _authed_headers(make_token, test_redis_client)
    resp = client.get("/api/billing/invoices", headers=headers)

    assert resp.status_code == 502
    assert resp.json()["detail"]["error"]["code"] == "service_unavailable"


def test_downstream_timeout_returns_504(client, monkeypatch, make_token, test_redis_client):
    async def _fake_forward(method, url, params, content, headers):
        raise httpx.TimeoutException("simulated timeout", request=httpx.Request(method, url))

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    headers = _authed_headers(make_token, test_redis_client)
    resp = client.get("/api/usage/summary", headers=headers)

    assert resp.status_code == 504
    assert resp.json()["detail"]["error"]["code"] == "upstream_timeout"


def test_public_route_reaches_downstream_without_any_token(client, monkeypatch):
    """Confirms is_public_route actually takes effect inside the proxy —
    not just correct in isolation (that's covered separately in
    test_jwt_verification.py)."""

    async def _fake_forward(method, url, params, content, headers):
        return httpx.Response(200, json={"tokens": "issued"})

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    resp = client.post("/api/auth/login", json={"email": "a@b.com", "password": "x"})
    assert resp.status_code == 200

def test_null_account_id_rejected_on_non_auth_route(client, monkeypatch, make_token, test_redis_client):
    """A freshly logged-in, not-yet-scoped token must not be usable against
    account-scoped downstream routes — see docs/ARCHITECTURE.md."""

    async def _fake_forward(method, url, params, content, headers):
        raise AssertionError("should never reach downstream — rejected at the gateway")

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    token = make_token(jti="unscoped-jti", account_id=None)
    test_redis_client.setex("jti:unscoped-jti", 900, "1")

    resp = client.get("/api/accounts/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "account_scope_required"


def test_null_account_id_still_allowed_on_auth_route(client, monkeypatch, make_token, test_redis_client):
    """The auth prefix itself must stay reachable with an unscoped token —
    it's the exchange path a client uses to GET a scoped one."""

    async def _fake_forward(method, url, params, content, headers):
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    token = make_token(jti="unscoped-jti-2", account_id=None)
    test_redis_client.setex("jti:unscoped-jti-2", 900, "1")

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200


def test_scoped_account_id_passes_through_to_downstream(client, monkeypatch, make_token, test_redis_client):
    """Sanity check the guard doesn't false-positive on a normal, already-
    scoped token — this is the common case and must keep working."""

    async def _fake_forward(method, url, params, content, headers):
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    headers = _authed_headers(make_token, test_redis_client)  # account_id="account-1" per fixture default
    resp = client.get("/api/accounts/me", headers=headers)

    assert resp.status_code == 200

def test_null_account_id_allowed_on_switch_route(client, monkeypatch, make_token, test_redis_client):
    """The whole point of /accounts/{id}/switch is taking an unscoped
    token to a scoped one — it must not be blocked by the guard it
    exists to route around."""

    async def _fake_forward(method, url, params, content, headers):
        return httpx.Response(200, json={"access_token": "scoped", "account_id": "x", "role": "owner"})

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    token = make_token(jti="unscoped-jti-3", account_id=None)
    test_redis_client.setex("jti:unscoped-jti-3", 900, "1")

    resp = client.post(
        "/api/accounts/0e8fe180-c1ea-4a1f-bbca-8bc6f68ce470/switch",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200


def test_null_account_id_allowed_on_accounts_mine(client, monkeypatch, make_token, test_redis_client):
    async def _fake_forward(method, url, params, content, headers):
        return httpx.Response(200, json=[])

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    token = make_token(jti="unscoped-jti-4", account_id=None)
    test_redis_client.setex("jti:unscoped-jti-4", 900, "1")

    resp = client.get("/api/accounts/mine", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200


def test_null_account_id_allowed_on_invite_accept(client, monkeypatch, make_token, test_redis_client):
    async def _fake_forward(method, url, params, content, headers):
        return httpx.Response(200, json={"access_token": "scoped", "account_id": "x", "role": "member"})

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    token = make_token(jti="unscoped-jti-5", account_id=None)
    test_redis_client.setex("jti:unscoped-jti-5", 900, "1")

    resp = client.post("/api/invites/some-raw-token/accept", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200


def test_null_account_id_still_rejected_on_member_management(client, monkeypatch, make_token, test_redis_client):
    """Sibling routes under the same 'accounts' prefix must NOT be swept
    up by the switch/mine/create exemptions — this is the regression this
    test guards against."""

    async def _fake_forward(method, url, params, content, headers):
        raise AssertionError("should never reach downstream — rejected at the gateway")

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    token = make_token(jti="unscoped-jti-6", account_id=None)
    test_redis_client.setex("jti:unscoped-jti-6", 900, "1")

    resp = client.patch(
        "/api/accounts/some-id/members/some-user",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "admin"},
    )

    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "account_scope_required"