from app.models import RefreshToken


def _signup_and_verify(client, published_events, email="alice@example.com", password="Passw0rd!"):
    client.post("/auth/signup", json={"email": email, "password": password})
    raw_token = published_events[0]["payload"]["verification_token"]
    client.post("/auth/verify-email", json={"token": raw_token})
    published_events.clear()  # so later assertions on this list only see post-login events


def test_login_succeeds_and_returns_token_pair(client, published_events):
    _signup_and_verify(client, published_events)

    response = client.post("/auth/login", json={"email": "alice@example.com", "password": "Passw0rd!"})

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


def test_login_publishes_user_logged_in_event(client, published_events):
    _signup_and_verify(client, published_events)

    client.post("/auth/login", json={"email": "alice@example.com", "password": "Passw0rd!"})

    assert any(e["event_type"] == "user.logged_in" for e in published_events)


def test_login_rejects_wrong_password(client, published_events):
    _signup_and_verify(client, published_events)

    response = client.post("/auth/login", json={"email": "alice@example.com", "password": "WrongPassword!"})

    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "invalid_credentials"


def test_login_rejects_unverified_account(client, published_events):
    client.post("/auth/signup", json={"email": "unverified@example.com", "password": "Passw0rd!"})
    # deliberately skip verify-email

    response = client.post("/auth/login", json={"email": "unverified@example.com", "password": "Passw0rd!"})

    assert response.status_code == 403
    assert response.json()["detail"]["error"]["code"] == "email_not_verified"


def test_login_rate_limit_trips_after_max_attempts(client, published_events):
    _signup_and_verify(client, published_events)

    for _ in range(5):
        r = client.post("/auth/login", json={"email": "alice@example.com", "password": "WrongPassword!"})
        assert r.status_code == 401

    sixth = client.post("/auth/login", json={"email": "alice@example.com", "password": "WrongPassword!"})
    assert sixth.status_code == 429
    assert sixth.json()["detail"]["error"]["code"] == "too_many_attempts"


def test_refresh_rotates_token_and_old_one_stops_working(client, published_events, db_session):
    _signup_and_verify(client, published_events)
    login_resp = client.post("/auth/login", json={"email": "alice@example.com", "password": "Passw0rd!"})
    original_refresh = login_resp.json()["refresh_token"]

    first_refresh = client.post("/auth/refresh", json={"refresh_token": original_refresh})
    assert first_refresh.status_code == 200
    new_refresh = first_refresh.json()["refresh_token"]
    assert new_refresh != original_refresh

    # Reuse detection: the OLD token, now that it's been rotated, must fail.
    reuse_attempt = client.post("/auth/refresh", json={"refresh_token": original_refresh})
    assert reuse_attempt.status_code == 401
    assert reuse_attempt.json()["detail"]["error"]["code"] == "refresh_token_reused"

    # The chain is actually recorded, not just rejected — confirms
    # rotated_from linkage described in the RefreshToken model.
    old_row = db_session.query(RefreshToken).filter(RefreshToken.token_hash != None).all()
    assert any(row.rotated_from is not None for row in old_row)


def test_logout_revokes_refresh_token_and_removes_jti(client, published_events, test_redis_client):
    _signup_and_verify(client, published_events)
    login_resp = client.post("/auth/login", json={"email": "alice@example.com", "password": "Passw0rd!"})
    access_token = login_resp.json()["access_token"]
    refresh_token = login_resp.json()["refresh_token"]

    assert len(test_redis_client.keys("jti:*")) == 1  # confirms login actually stored it

    logout_resp = client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert logout_resp.status_code == 200
    assert len(test_redis_client.keys("jti:*")) == 0

    # The now-revoked refresh token must also fail if reused via /auth/refresh.
    reuse_attempt = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse_attempt.status_code == 401
    assert reuse_attempt.json()["detail"]["error"]["code"] == "refresh_token_reused"