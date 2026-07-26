import json

import httpx


def test_login_sets_httponly_cookie_and_strips_token_from_body(client, monkeypatch):
    async def _fake_forward(method, url, params, content, headers):
        return httpx.Response(200, json={"access_token": "acc123", "refresh_token": "raw-refresh-xyz", "token_type": "bearer"})

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    resp = client.post("/api/auth/login", json={"email": "a@b.com", "password": "hunter22"})

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"access_token": "acc123", "token_type": "bearer"}
    assert "refresh_token" not in body

    cookie = resp.cookies.get("refresh_token")
    assert cookie == "raw-refresh-xyz"
    set_cookie_header = resp.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie_header
    assert "Path=/api/auth" in set_cookie_header


def test_refresh_injects_cookie_value_into_forwarded_body(client, monkeypatch):
    captured = {}

    async def _fake_forward(method, url, params, content, headers):
        captured["content"] = content
        return httpx.Response(200, json={"access_token": "new-acc", "refresh_token": "new-raw-refresh", "token_type": "bearer"})

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    resp = client.post("/api/auth/refresh", json={}, cookies={"refresh_token": "old-raw-refresh"})

    assert resp.status_code == 200
    forwarded_body = json.loads(captured["content"])
    assert forwarded_body["refresh_token"] == "old-raw-refresh"
    assert resp.cookies.get("refresh_token") == "new-raw-refresh"


def test_logout_injects_cookie_and_clears_it(client, monkeypatch, make_token, test_redis_client):
    captured = {}

    async def _fake_forward(method, url, params, content, headers):
        captured["content"] = content
        return httpx.Response(200, json={"message": "Logged out."})

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)

    jti = "logout-test-jti"
    token = make_token(jti=jti)
    test_redis_client.setex(f"jti:{jti}", 900, "1")

    resp = client.post(
        "/api/auth/logout",
        json={},
        headers={"Authorization": f"Bearer {token}"},
        cookies={"refresh_token": "raw-to-clear"},
    )

    assert resp.status_code == 200
    forwarded_body = json.loads(captured["content"])
    assert forwarded_body["refresh_token"] == "raw-to-clear"
    set_cookie_header = resp.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie_header
    assert "Max-Age=0" in set_cookie_header or "expires=" in set_cookie_header.lower()