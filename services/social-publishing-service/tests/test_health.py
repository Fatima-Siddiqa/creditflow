def test_healthz_returns_ok(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_readyz_returns_ok(client):
    assert client.get("/readyz").status_code == 200