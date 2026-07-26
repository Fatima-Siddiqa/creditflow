import uuid

from app.config import settings
from app.models import User


def _signup_and_verify(client, published_events, email="alice@example.com", password="Passw0rd!"):
    client.post("/auth/signup", json={"email": email, "password": password})
    raw_token = published_events[0]["payload"]["verification_token"]
    client.post("/auth/verify-email", json={"token": raw_token})
    published_events.clear()


def _get_user_id(db_session, email="alice@example.com") -> str:
    return str(db_session.query(User).filter(User.email == email).first().id)


def test_get_user_email_rejects_missing_secret(client, published_events, db_session):
    _signup_and_verify(client, published_events)
    user_id = _get_user_id(db_session)

    response = client.get(f"/auth/internal/users/{user_id}")

    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "invalid_internal_secret"


def test_get_user_email_rejects_unknown_user(client, published_events):
    response = client.get(
        f"/auth/internal/users/{uuid.uuid4()}",
        headers={"X-Internal-Secret": settings.internal_service_secret},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "user_not_found"


def test_get_user_email_happy_path(client, published_events, db_session):
    _signup_and_verify(client, published_events, email="bob@example.com")
    user_id = _get_user_id(db_session, email="bob@example.com")

    response = client.get(
        f"/auth/internal/users/{user_id}",
        headers={"X-Internal-Secret": settings.internal_service_secret},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == user_id
    assert body["email"] == "bob@example.com"