def test_healthz_always_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_ok_when_db_reachable(client):
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_503_when_db_unreachable(client, monkeypatch):
    def _broken_connect():
        raise ConnectionError("simulated postgres outage")

    monkeypatch.setattr("app.main.engine.connect", _broken_connect)

    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"]["code"] == "not_ready"