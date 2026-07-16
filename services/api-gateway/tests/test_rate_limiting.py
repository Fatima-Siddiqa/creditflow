import httpx


def _mock_forward_ok(monkeypatch):
    async def _fake_forward(method, url, params, content, headers):
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("app.api.proxy._forward", _fake_forward)


def test_ip_rate_limit_triggers_429_on_public_route(client, monkeypatch):
    monkeypatch.setattr("app.config.settings.rate_limit_max_requests_per_ip", 3)
    _mock_forward_ok(monkeypatch)

    statuses = [
        client.post("/api/auth/login", json={"email": "a@b.com", "password": "x"}).status_code
        for _ in range(5)
    ]

    assert statuses[:3] == [200, 200, 200]
    assert 429 in statuses[3:]


def test_rate_limit_error_uses_standard_schema(client, monkeypatch):
    monkeypatch.setattr("app.config.settings.rate_limit_max_requests_per_ip", 1)
    _mock_forward_ok(monkeypatch)

    client.post("/api/auth/login", json={"email": "a@b.com", "password": "x"})
    resp = client.post("/api/auth/login", json={"email": "a@b.com", "password": "x"})

    assert resp.status_code == 429
    assert resp.json()["detail"]["error"]["code"] == "rate_limit_exceeded"


def test_account_rate_limit_triggers_429_independently_of_ip_limit(
    client, monkeypatch, make_token, test_redis_client
):
    monkeypatch.setattr("app.config.settings.rate_limit_max_requests_per_account", 2)
    _mock_forward_ok(monkeypatch)

    token = make_token(jti="rl-jti", account_id="acct-rl")
    test_redis_client.setex("jti:rl-jti", 900, "1")
    headers = {"Authorization": f"Bearer {token}"}

    statuses = [
        client.post("/api/auth/logout", headers=headers, json={"refresh_token": "x"}).status_code
        for _ in range(4)
    ]

    assert statuses[:2] == [200, 200]
    assert 429 in statuses[2:]


def test_ip_limit_checked_before_auth_so_it_also_blocks_unauthenticated_floods(client, monkeypatch):
    monkeypatch.setattr("app.config.settings.rate_limit_max_requests_per_ip", 1)

    first = client.post("/api/auth/logout", json={"refresh_token": "x"})
    second = client.post("/api/auth/logout", json={"refresh_token": "x"})

    assert first.status_code == 401  # missing_token — IP limit not yet hit
    assert second.status_code == 429  # IP limit now hit, before auth even runs


def test_sliding_window_prevents_boundary_burst(monkeypatch):
    """A pure fixed-window counter has a known flaw: max_requests can land
    right before a window boundary, then another max_requests right after
    -> ~2x the intended rate in a short burst. This proves that flaw does
    NOT exist here — a burst spanning a boundary is still capped near the
    real limit, not doubled."""
    import pytest
    from fastapi import HTTPException

    from app import rate_limiter

    window = 60
    monkeypatch.setattr("app.config.settings.rate_limit_window_seconds", window)

    # Align to an ACTUAL window boundary — an arbitrary timestamp like
    # 1_000_000 is NOT necessarily a multiple of `window`, so naively
    # adding "window - 1" to it doesn't reliably land at a real boundary.
    anchor = 1_000_000
    window_start = anchor - (anchor % window)
    fake_time = [window_start + window - 1]  # last second of this window
    monkeypatch.setattr("app.rate_limiter.time.time", lambda: fake_time[0])

    # Use up the full limit right at the end of this window.
    for _ in range(10):
        rate_limiter._check_limit("test", "boundary-ip", 10)
    with pytest.raises(HTTPException):
        rate_limiter._check_limit("test", "boundary-ip", 10)

    # Now genuinely cross into the next window (2 seconds past its start).
    fake_time[0] = window_start + window + 2

    # A fixed-window counter would allow a fresh 10 here. The sliding
    # blend should allow only a couple, since ~97% of the previous
    # window's count still weighs against the limit.
    allowed = 0
    try:
        for _ in range(10):
            rate_limiter._check_limit("test", "boundary-ip", 10)
            allowed += 1
    except HTTPException:
        pass

    assert allowed < 5