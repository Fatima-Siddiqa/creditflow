import httpx


def _mock_forward_ok(monkeypatch):
    async def _fake_forward(method, url, params, content, headers):
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)


def test_protected_route_without_header_returns_401_missing_token(client):
    resp = client.post("/api/auth/logout", json={"refresh_token": "x"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "missing_token"


def test_protected_route_with_malformed_bearer_returns_401_missing_token(client):
    resp = client.post("/api/auth/logout", headers={"Authorization": "garbage"}, json={"refresh_token": "x"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "missing_token"


def test_malformed_jwt_returns_401_invalid_token(client):
    resp = client.post(
        "/api/auth/logout",
        headers={"Authorization": "Bearer not-a-real-jwt"},
        json={"refresh_token": "x"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "invalid_token"


def test_expired_token_returns_401_token_expired(client, make_token):
    token = make_token(jti="expired-jti", expired=True)
    resp = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
        json={"refresh_token": "x"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "token_expired"


def test_valid_token_but_jti_not_in_redis_returns_401_session_revoked(client, make_token):
    token = make_token(jti="never-issued-jti")
    resp = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
        json={"refresh_token": "x"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "session_revoked"


def test_valid_token_with_active_jti_passes_through(client, monkeypatch, make_token, test_redis_client):
    _mock_forward_ok(monkeypatch)
    token = make_token(jti="active-jti")
    test_redis_client.setex("jti:active-jti", 900, "1")

    resp = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
        json={"refresh_token": "x"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_public_route_bypasses_jwt_entirely(client, monkeypatch):
    _mock_forward_ok(monkeypatch)
    resp = client.post("/api/auth/login", json={"email": "a@b.com", "password": "x"})
    assert resp.status_code == 200