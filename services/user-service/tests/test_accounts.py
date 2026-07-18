import uuid

from app.models import Account, AccountMember


def _seed_membership(db_session, user_id, role="owner", account_type="team", name="Acme"):
    account = Account(type=account_type, name=name, plan_tier="free")
    db_session.add(account)
    db_session.flush()
    db_session.add(AccountMember(account_id=account.id, user_id=user_id, role=role))
    db_session.commit()
    return account


def test_endpoints_require_auth(client):
    resp = client.post("/accounts", json={"name": "Acme"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "missing_token"


def test_create_team_account_makes_caller_owner(client, make_token, test_redis_client, db_session, published_events):
    user_id = uuid.uuid4()
    token = make_token(jti="j1", sub=str(user_id))
    test_redis_client.setex("jti:j1", 900, "1")

    resp = client.post("/accounts", json={"name": "Acme"}, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "team"
    assert body["name"] == "Acme"
    assert body["seat_count"] == 1

    membership = (
        db_session.query(AccountMember)
        .filter(AccountMember.account_id == uuid.UUID(body["id"]))
        .one()
    )
    assert membership.user_id == user_id
    assert membership.role == "owner"

    assert len(published_events) == 1
    assert published_events[0]["event_type"] == "account.created"
    assert published_events[0]["payload"]["account_id"] == body["id"]


def test_create_team_account_works_with_account_agnostic_token(client, make_token, test_redis_client):
    """A plain login token (account_id/role both null) is enough to
    create a new account — you don't need to already belong to one."""
    user_id = uuid.uuid4()
    token = make_token(jti="j2", sub=str(user_id), account_id=None, role=None)
    test_redis_client.setex("jti:j2", 900, "1")

    resp = client.post("/accounts", json={"name": "NewCo"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201


def test_get_account_profile_as_member(client, make_token, test_redis_client, db_session):
    user_id = uuid.uuid4()
    account = _seed_membership(db_session, user_id, role="member")
    token = make_token(jti="j3", sub=str(user_id))
    test_redis_client.setex("jti:j3", 900, "1")

    resp = client.get(f"/accounts/{account.id}", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(account.id)
    assert body["seat_count"] == 1


def test_get_account_profile_rejects_non_member(client, make_token, test_redis_client, db_session):
    owner_id = uuid.uuid4()
    account = _seed_membership(db_session, owner_id, role="owner")

    stranger_id = uuid.uuid4()
    token = make_token(jti="j4", sub=str(stranger_id))
    test_redis_client.setex("jti:j4", 900, "1")

    resp = client.get(f"/accounts/{account.id}", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "not_a_member"


def test_get_account_profile_seat_count_reflects_multiple_members(client, make_token, test_redis_client, db_session):
    owner_id = uuid.uuid4()
    account = _seed_membership(db_session, owner_id, role="owner")
    db_session.add(AccountMember(account_id=account.id, user_id=uuid.uuid4(), role="member"))
    db_session.add(AccountMember(account_id=account.id, user_id=uuid.uuid4(), role="member"))
    db_session.commit()

    token = make_token(jti="j5", sub=str(owner_id))
    test_redis_client.setex("jti:j5", 900, "1")

    resp = client.get(f"/accounts/{account.id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["seat_count"] == 3


def test_list_mine_returns_all_memberships(client, make_token, test_redis_client, db_session):
    user_id = uuid.uuid4()
    _seed_membership(db_session, user_id, role="owner", name="First")
    _seed_membership(db_session, user_id, role="member", name="Second")

    token = make_token(jti="j6", sub=str(user_id))
    test_redis_client.setex("jti:j6", 900, "1")

    resp = client.get("/accounts/mine", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    names = {entry["name"] for entry in body}
    assert names == {"First", "Second"}
    roles_by_name = {entry["name"]: entry["role"] for entry in body}
    assert roles_by_name["First"] == "owner"
    assert roles_by_name["Second"] == "member"


def test_list_mine_is_scoped_to_the_calling_user(client, make_token, test_redis_client, db_session):
    """Two different users, each a member of their own account — user A's
    /accounts/mine must never include user B's account, and vice versa.
    Replaces the old test_cannot_list_another_users_accounts, which tested
    a user_id path param that no longer exists now that caller identity
    comes from the JWT alone (see GET /accounts/mine)."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    _seed_membership(db_session, user_a, role="owner", name="Account A")
    _seed_membership(db_session, user_b, role="owner", name="Account B")

    token_a = make_token(jti="j7", sub=str(user_a))
    test_redis_client.setex("jti:j7", 900, "1")
    token_b = make_token(jti="j8", sub=str(user_b))
    test_redis_client.setex("jti:j8", 900, "1")

    resp_a = client.get("/accounts/mine", headers={"Authorization": f"Bearer {token_a}"})
    resp_b = client.get("/accounts/mine", headers={"Authorization": f"Bearer {token_b}"})

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    names_a = {entry["name"] for entry in resp_a.json()}
    names_b = {entry["name"] for entry in resp_b.json()}

    assert names_a == {"Account A"}
    assert names_b == {"Account B"}