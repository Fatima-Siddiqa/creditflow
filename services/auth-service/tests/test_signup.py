from app.models import User, Credential


def test_signup_creates_user(client, db_session):
    response = client.post("/auth/signup", json={"email": "alice@example.com", "password": "Passw0rd!"})

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert body["is_verified"] is False

    user = db_session.query(User).filter(User.email == "alice@example.com").first()
    assert user is not None
    credential = db_session.query(Credential).filter(Credential.user_id == user.id).first()
    assert credential is not None
    assert credential.password_hash != "Passw0rd!"  # confirms it's actually hashed, not stored raw


def test_signup_publishes_user_registered_event(client, published_events):
    client.post("/auth/signup", json={"email": "bob@example.com", "password": "Passw0rd!"})

    assert len(published_events) == 1
    assert published_events[0]["event_type"] == "user.registered"
    assert published_events[0]["payload"]["email"] == "bob@example.com"


def test_signup_rejects_duplicate_email(client):
    client.post("/auth/signup", json={"email": "carol@example.com", "password": "Passw0rd!"})
    response = client.post("/auth/signup", json={"email": "carol@example.com", "password": "AnotherPass1!"})

    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "email_already_registered"


def test_verify_email_with_real_token_from_event(client, published_events, db_session):
    client.post("/auth/signup", json={"email": "erin@example.com", "password": "Passw0rd!"})
    raw_token = published_events[0]["payload"]["verification_token"]

    response = client.post("/auth/verify-email", json={"token": raw_token})

    assert response.status_code == 200
    user = db_session.query(User).filter(User.email == "erin@example.com").first()
    assert user.is_verified is True


def test_verify_email_rejects_invalid_token(client):
    response = client.post("/auth/verify-email", json={"token": "not-a-real-token"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "invalid_token"


def test_verify_email_rejects_reused_token(client, published_events):
    client.post("/auth/signup", json={"email": "frank@example.com", "password": "Passw0rd!"})
    raw_token = published_events[0]["payload"]["verification_token"]

    first = client.post("/auth/verify-email", json={"token": raw_token})
    second = client.post("/auth/verify-email", json={"token": raw_token})

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["detail"]["error"]["code"] == "token_already_used"