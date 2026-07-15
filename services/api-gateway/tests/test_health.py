def test_healthz_always_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_ok_when_redis_reachable(client):
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_503_when_redis_unreachable(client, monkeypatch):
    def _broken_ping():
        raise ConnectionError("simulated redis outage")

    monkeypatch.setattr("app.main.redis_client.ping", _broken_ping)

    resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["error"]["code"] == "not_ready"