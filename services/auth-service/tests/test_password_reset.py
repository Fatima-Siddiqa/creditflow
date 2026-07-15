from app.models import RefreshToken


def _signup_and_verify(client, published_events, email="alice@example.com", password="Passw0rd!"):
    client.post("/auth/signup", json={"email": email, "password": password})
    raw_token = published_events[0]["payload"]["verification_token"]
    client.post("/auth/verify-email", json={"token": raw_token})
    published_events.clear()


def test_forgot_password_publishes_event_with_otp(client, published_events):
    _signup_and_verify(client, published_events)

    response = client.post("/auth/forgot-password", json={"email": "alice@example.com"})

    assert response.status_code == 200
    assert len(published_events) == 1
    assert published_events[0]["event_type"] == "user.password_reset_requested"
    otp = published_events[0]["payload"]["otp"]
    assert len(otp) == 6
    assert otp.isdigit()


def test_forgot_password_gives_same_response_for_unknown_email(client, published_events):
    # Deliberately not revealing whether the email is registered — see
    # comment in the endpoint itself for why this matters.
    known = client.post("/auth/forgot-password", json={"email": "unknown@example.com"})

    assert known.status_code == 200
    assert known.json()["message"] == "If that email is registered, a reset code has been sent."
    assert len(published_events) == 0  # no event for an email that doesn't exist


def test_reset_password_succeeds_with_valid_otp(client, published_events):
    _signup_and_verify(client, published_events)
    client.post("/auth/forgot-password", json={"email": "alice@example.com"})
    otp = published_events[-1]["payload"]["otp"]

    response = client.post("/auth/reset-password", json={"token": otp, "new_password": "NewPassw0rd!"})
    assert response.status_code == 200

    # Confirm the new password actually works and the old one doesn't.
    old_login = client.post("/auth/login", json={"email": "alice@example.com", "password": "Passw0rd!"})
    assert old_login.status_code == 401

    new_login = client.post("/auth/login", json={"email": "alice@example.com", "password": "NewPassw0rd!"})
    assert new_login.status_code == 200


def test_reset_password_rejects_reused_otp(client, published_events):
    _signup_and_verify(client, published_events)
    client.post("/auth/forgot-password", json={"email": "alice@example.com"})
    otp = published_events[-1]["payload"]["otp"]

    first = client.post("/auth/reset-password", json={"token": otp, "new_password": "NewPassw0rd!"})
    second = client.post("/auth/reset-password", json={"token": otp, "new_password": "AnotherPass1!"})

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["detail"]["error"]["code"] == "token_already_used"


def test_reset_password_rejects_invalid_otp(client):
    response = client.post("/auth/reset-password", json={"token": "000000", "new_password": "NewPassw0rd!"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "invalid_token"


def test_reset_password_revokes_existing_sessions(client, published_events, db_session):
    _signup_and_verify(client, published_events)
    login_resp = client.post("/auth/login", json={"email": "alice@example.com", "password": "Passw0rd!"})
    old_refresh = login_resp.json()["refresh_token"]

    client.post("/auth/forgot-password", json={"email": "alice@example.com"})
    otp = published_events[-1]["payload"]["otp"]
    client.post("/auth/reset-password", json={"token": otp, "new_password": "NewPassw0rd!"})

    # The refresh token issued before the reset must now be dead — this is
    # the specific security-correctness behavior we added by hand earlier,
    # confirming it's not just present in the code but actually enforced.
    reuse_attempt = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse_attempt.status_code == 401