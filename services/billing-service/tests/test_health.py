def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_readyz_ok(client):
    assert client.get("/readyz").status_code == 200