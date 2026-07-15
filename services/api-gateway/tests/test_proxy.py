import httpx

from app.config import settings


def test_unknown_prefix_returns_404(client):
    resp = client.get("/api/nonexistent/ping")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "route_not_found"


def test_known_prefix_forwards_to_correct_service_url(client, monkeypatch):
    captured = {}

    async def _fake_forward(method, url, params, content, headers):
        captured["method"] = method
        captured["url"] = url
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    resp = client.get("/api/auth/me")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert captured["method"] == "GET"
    # /api stripped, rest of the path preserved as-is for the downstream
    # service's own router (auth-service's router prefix is "/auth").
    assert captured["url"] == f"{settings.auth_service_url}/auth/me"


def test_downstream_connection_error_returns_502(client, monkeypatch):
    async def _fake_forward(method, url, params, content, headers):
        raise httpx.ConnectError("simulated: service not built yet", request=httpx.Request(method, url))

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    resp = client.get("/api/billing/invoices")

    assert resp.status_code == 502
    assert resp.json()["detail"]["error"]["code"] == "service_unavailable"


def test_downstream_timeout_returns_504(client, monkeypatch):
    async def _fake_forward(method, url, params, content, headers):
        raise httpx.TimeoutException("simulated timeout", request=httpx.Request(method, url))

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    resp = client.get("/api/usage/summary")

    assert resp.status_code == 504
    assert resp.json()["detail"]["error"]["code"] == "upstream_timeout"