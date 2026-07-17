import uuid

from app.config import settings
from app.models import User
from app.security import decode_access_token


def _signup_and_verify(client, published_events, email="alice@example.com", password="Passw0rd!"):
    client.post("/auth/signup", json={"email": email, "password": password})
    raw_token = published_events[0]["payload"]["verification_token"]
    client.post("/auth/verify-email", json={"token": raw_token})
    published_events.clear()


def _get_user_id(db_session, email="alice@example.com") -> str:
    return str(db_session.query(User).filter(User.email == email).first().id)


def test_issue_scoped_token_rejects_missing_secret(client, published_events, db_session):
    _signup_and_verify(client, published_events)
    user_id = _get_user_id(db_session)

    response = client.post(
        "/auth/issue-scoped-token",
        json={"user_id": user_id, "account_id": str(uuid.uuid4()), "role": "owner"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "invalid_internal_secret"


def test_issue_scoped_token_rejects_wrong_secret(client, published_events, db_session):
    _signup_and_verify(client, published_events)
    user_id = _get_user_id(db_session)

    response = client.post(
        "/auth/issue-scoped-token",
        json={"user_id": user_id, "account_id": str(uuid.uuid4()), "role": "owner"},
        headers={"X-Internal-Secret": "not-the-real-secret"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "invalid_internal_secret"


def test_issue_scoped_token_rejects_unknown_user(client, published_events):
    response = client.post(
        "/auth/issue-scoped-token",
        json={"user_id": str(uuid.uuid4()), "account_id": str(uuid.uuid4()), "role": "owner"},
        headers={"X-Internal-Secret": settings.internal_service_secret},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "user_not_found"


def test_issue_scoped_token_rejects_unverified_user(client, published_events, db_session):
    client.post("/auth/signup", json={"email": "unverified@example.com", "password": "Passw0rd!"})
    published_events.clear()
    user_id = _get_user_id(db_session, email="unverified@example.com")

    response = client.post(
        "/auth/issue-scoped-token",
        json={"user_id": user_id, "account_id": str(uuid.uuid4()), "role": "owner"},
        headers={"X-Internal-Secret": settings.internal_service_secret},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error"]["code"] == "email_not_verified"


def test_issue_scoped_token_happy_path(client, published_events, db_session, test_redis_client):
    _signup_and_verify(client, published_events)
    user_id = _get_user_id(db_session)
    account_id = str(uuid.uuid4())

    response = client.post(
        "/auth/issue-scoped-token",
        json={"user_id": user_id, "account_id": account_id, "role": "owner"},
        headers={"X-Internal-Secret": settings.internal_service_secret},
    )

    assert response.status_code == 200
    body = response.json()
    assert "refresh_token" not in body  # scoped issuance is access-token-only, see schema docstring
    assert body["token_type"] == "bearer"

    payload = decode_access_token(body["access_token"])
    assert payload["sub"] == user_id
    assert payload["account_id"] == account_id
    assert payload["role"] == "owner"
    assert test_redis_client.exists(f"jti:{payload['jti']}")


def test_issue_scoped_token_does_not_revoke_other_account_sessions(client, published_events, db_session, test_redis_client):
    """A user switching to account B shouldn't kill their still-open session
    on account A — both jtis should remain valid simultaneously."""
    _signup_and_verify(client, published_events)
    user_id = _get_user_id(db_session)

    first = client.post(
        "/auth/issue-scoped-token",
        json={"user_id": user_id, "account_id": str(uuid.uuid4()), "role": "owner"},
        headers={"X-Internal-Secret": settings.internal_service_secret},
    )
    second = client.post(
        "/auth/issue-scoped-token",
        json={"user_id": user_id, "account_id": str(uuid.uuid4()), "role": "member"},
        headers={"X-Internal-Secret": settings.internal_service_secret},
    )

    first_jti = decode_access_token(first.json()["access_token"])["jti"]
    second_jti = decode_access_token(second.json()["access_token"])["jti"]

    assert test_redis_client.exists(f"jti:{first_jti}")
    assert test_redis_client.exists(f"jti:{second_jti}")