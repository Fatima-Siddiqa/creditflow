import uuid

from app.models import Account, AccountMember


def _seed_account(db_session, owner_id, extra_members=None, name="Acme"):
    """extra_members: list of (user_id, role) tuples."""
    account = Account(type="team", name=name, plan_tier="free")
    db_session.add(account)
    db_session.flush()
    db_session.add(AccountMember(account_id=account.id, user_id=owner_id, role="owner"))
    for user_id, role in (extra_members or []):
        db_session.add(AccountMember(account_id=account.id, user_id=user_id, role=role))
    db_session.commit()
    return account


def _auth(make_token, test_redis_client, jti, user_id):
    token = make_token(jti=jti, sub=str(user_id))
    test_redis_client.setex(f"jti:{jti}", 900, "1")
    return {"Authorization": f"Bearer {token}"}


# ---- update_member_role ----

def test_owner_can_promote_member_to_admin(client, make_token, test_redis_client, db_session, published_events):
    owner_id = uuid.uuid4()
    member_id = uuid.uuid4()
    account = _seed_account(db_session, owner_id, extra_members=[(member_id, "member")])

    resp = client.patch(
        f"/accounts/{account.id}/members/{member_id}",
        json={"role": "admin"},
        headers=_auth(make_token, test_redis_client, "m1", owner_id),
    )

    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"

    db_session.expire_all()
    updated = db_session.query(AccountMember).filter(
        AccountMember.account_id == account.id, AccountMember.user_id == member_id
    ).one()
    assert updated.role == "admin"

    role_updated = [e for e in published_events if e["event_type"] == "member.role_updated"]
    assert len(role_updated) == 1
    assert role_updated[0]["payload"]["role"] == "admin"


def test_member_cannot_update_roles(client, make_token, test_redis_client, db_session):
    owner_id = uuid.uuid4()
    member_id = uuid.uuid4()
    target_id = uuid.uuid4()
    account = _seed_account(db_session, owner_id, extra_members=[(member_id, "member"), (target_id, "member")])

    resp = client.patch(
        f"/accounts/{account.id}/members/{target_id}",
        json={"role": "admin"},
        headers=_auth(make_token, test_redis_client, "m2", member_id),
    )

    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "insufficient_role"


def test_cannot_demote_the_last_owner(client, make_token, test_redis_client, db_session):
    owner_id = uuid.uuid4()
    account = _seed_account(db_session, owner_id)

    resp = client.patch(
        f"/accounts/{account.id}/members/{owner_id}",
        json={"role": "admin"},
        headers=_auth(make_token, test_redis_client, "m3", owner_id),
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "last_owner"


def test_can_demote_an_owner_when_another_owner_exists(client, make_token, test_redis_client, db_session):
    owner_id = uuid.uuid4()
    second_owner_id = uuid.uuid4()
    account = _seed_account(db_session, owner_id, extra_members=[(second_owner_id, "owner")])

    resp = client.patch(
        f"/accounts/{account.id}/members/{second_owner_id}",
        json={"role": "admin"},
        headers=_auth(make_token, test_redis_client, "m4", owner_id),
    )

    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


def test_update_role_rejects_invalid_role(client, make_token, test_redis_client, db_session):
    owner_id = uuid.uuid4()
    member_id = uuid.uuid4()
    account = _seed_account(db_session, owner_id, extra_members=[(member_id, "member")])

    resp = client.patch(
        f"/accounts/{account.id}/members/{member_id}",
        json={"role": "superadmin"},
        headers=_auth(make_token, test_redis_client, "m5", owner_id),
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "invalid_role"


def test_update_role_404_for_non_member_target(client, make_token, test_redis_client, db_session):
    owner_id = uuid.uuid4()
    account = _seed_account(db_session, owner_id)
    stranger_id = uuid.uuid4()

    resp = client.patch(
        f"/accounts/{account.id}/members/{stranger_id}",
        json={"role": "admin"},
        headers=_auth(make_token, test_redis_client, "m6", owner_id),
    )

    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "member_not_found"


# ---- remove_member ----

def test_owner_can_remove_a_member(client, make_token, test_redis_client, db_session, published_events):
    owner_id = uuid.uuid4()
    member_id = uuid.uuid4()
    account = _seed_account(db_session, owner_id, extra_members=[(member_id, "member")])

    resp = client.delete(
        f"/accounts/{account.id}/members/{member_id}",
        headers=_auth(make_token, test_redis_client, "m7", owner_id),
    )

    assert resp.status_code == 204

    db_session.expire_all()
    remaining = db_session.query(AccountMember).filter(
        AccountMember.account_id == account.id, AccountMember.user_id == member_id
    ).first()
    assert remaining is None

    removed = [e for e in published_events if e["event_type"] == "member.removed"]
    assert len(removed) == 1
    assert removed[0]["payload"]["user_id"] == str(member_id)


def test_cannot_remove_the_last_owner(client, make_token, test_redis_client, db_session):
    owner_id = uuid.uuid4()
    account = _seed_account(db_session, owner_id)

    resp = client.delete(
        f"/accounts/{account.id}/members/{owner_id}",
        headers=_auth(make_token, test_redis_client, "m8", owner_id),
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "last_owner"


def test_can_remove_an_owner_when_another_owner_exists(client, make_token, test_redis_client, db_session):
    owner_id = uuid.uuid4()
    second_owner_id = uuid.uuid4()
    account = _seed_account(db_session, owner_id, extra_members=[(second_owner_id, "owner")])

    resp = client.delete(
        f"/accounts/{account.id}/members/{second_owner_id}",
        headers=_auth(make_token, test_redis_client, "m9", owner_id),
    )

    assert resp.status_code == 204


def test_member_cannot_remove_others(client, make_token, test_redis_client, db_session):
    owner_id = uuid.uuid4()
    member_id = uuid.uuid4()
    target_id = uuid.uuid4()
    account = _seed_account(db_session, owner_id, extra_members=[(member_id, "member"), (target_id, "member")])

    resp = client.delete(
        f"/accounts/{account.id}/members/{target_id}",
        headers=_auth(make_token, test_redis_client, "m10", member_id),
    )

    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "insufficient_role"


def test_remove_member_404_for_non_member_target(client, make_token, test_redis_client, db_session):
    owner_id = uuid.uuid4()
    account = _seed_account(db_session, owner_id)
    stranger_id = uuid.uuid4()

    resp = client.delete(
        f"/accounts/{account.id}/members/{stranger_id}",
        headers=_auth(make_token, test_redis_client, "m11", owner_id),
    )

    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "member_not_found"