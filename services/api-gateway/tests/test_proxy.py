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