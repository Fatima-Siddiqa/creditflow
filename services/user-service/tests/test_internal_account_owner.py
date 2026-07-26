import uuid

from app.config import settings
from app.models import Account, AccountMember


def _seed_account(db_session, owner_id, name="Acme"):
    account = Account(type="team", name=name, plan_tier="free")
    db_session.add(account)
    db_session.flush()
    db_session.add(AccountMember(account_id=account.id, user_id=owner_id, role="owner"))
    db_session.commit()
    return account


def test_get_account_owner_rejects_missing_secret(client, db_session):
    owner_id = uuid.uuid4()
    account = _seed_account(db_session, owner_id)

    response = client.get(f"/accounts/internal/{account.id}/owner")

    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "invalid_internal_secret"


def test_get_account_owner_rejects_unknown_account(client):
    response = client.get(
        f"/accounts/internal/{uuid.uuid4()}/owner",
        headers={"X-Internal-Secret": settings.internal_service_secret},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "owner_not_found"


def test_get_account_owner_happy_path(client, db_session):
    owner_id = uuid.uuid4()
    account = _seed_account(db_session, owner_id)

    response = client.get(
        f"/accounts/internal/{account.id}/owner",
        headers={"X-Internal-Secret": settings.internal_service_secret},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["account_id"] == str(account.id)
    assert body["user_id"] == str(owner_id)
    assert body["role"] == "owner"