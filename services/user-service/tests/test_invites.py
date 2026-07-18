import uuid
from datetime import datetime, timedelta, timezone

from app.models import Account, AccountMember, Invite


def _seed_account_with_owner(db_session, owner_id, name="Acme"):
    account = Account(type="team", name=name, plan_tier="free")
    db_session.add(account)
    db_session.flush()
    db_session.add(AccountMember(account_id=account.id, user_id=owner_id, role="owner"))
    db_session.commit()
    return account


def _seed_invite(db_session, account_id, role="member", email="new@example.com", expired=False):
    from app.security import generate_raw_token, hash_token

    raw_token = generate_raw_token()
    invite = Invite(
        account_id=account_id,
        email=email,
        role=role,
        token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + (timedelta(days=-1) if expired else timedelta(days=7)),
    )
    db_session.add(invite)
    db_session.commit()
    return invite, raw_token


# ---- create_invite ----

def test_owner_can_create_invite(client, make_token, test_redis_client, db_session, published_events):
    owner_id = uuid.uuid4()
    account = _seed_account_with_owner(db_session, owner_id)
    token = make_token(jti="i1", sub=str(owner_id))
    test_redis_client.setex("jti:i1", 900, "1")

    resp = client.post(
        f"/accounts/{account.id}/invites",
        json={"email": "new@example.com", "role": "member"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "new@example.com"
    assert body["role"] == "member"
    assert body["accepted"] is False

    assert published_events[0]["event_type"] == "invite.created"


def test_member_cannot_create_invite(client, make_token, test_redis_client, db_session):
    owner_id = uuid.uuid4()
    account = _seed_account_with_owner(db_session, owner_id)
    member_id = uuid.uuid4()
    db_session.add(AccountMember(account_id=account.id, user_id=member_id, role="member"))
    db_session.commit()

    token = make_token(jti="i2", sub=str(member_id))
    test_redis_client.setex("jti:i2", 900, "1")

    resp = client.post(
        f"/accounts/{account.id}/invites",
        json={"email": "new@example.com", "role": "member"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "insufficient_role"


def test_non_member_cannot_create_invite(client, make_token, test_redis_client, db_session):
    owner_id = uuid.uuid4()
    account = _seed_account_with_owner(db_session, owner_id)
    stranger_token = make_token(jti="i3", sub=str(uuid.uuid4()))
    test_redis_client.setex("jti:i3", 900, "1")

    resp = client.post(
        f"/accounts/{account.id}/invites",
        json={"email": "new@example.com", "role": "member"},
        headers={"Authorization": f"Bearer {stranger_token}"},
    )

    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "not_a_member"


def test_create_invite_rejects_invalid_role(client, make_token, test_redis_client, db_session):
    owner_id = uuid.uuid4()
    account = _seed_account_with_owner(db_session, owner_id)
    token = make_token(jti="i4", sub=str(owner_id))
    test_redis_client.setex("jti:i4", 900, "1")

    resp = client.post(
        f"/accounts/{account.id}/invites",
        json={"email": "new@example.com", "role": "superadmin"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "invalid_role"


# ---- accept_invite ----

def test_accept_invite_creates_membership_and_returns_scoped_token(
    client, make_token, test_redis_client, db_session, published_events, fake_scoped_token,
):
    owner_id = uuid.uuid4()
    account = _seed_account_with_owner(db_session, owner_id)
    invite, raw_token = _seed_invite(db_session, account.id, role="member")

    invitee_id = uuid.uuid4()
    invitee_token = make_token(jti="i5", sub=str(invitee_id))
    test_redis_client.setex("jti:i5", 900, "1")

    resp = client.post(
        f"/invites/{raw_token}/accept",
        headers={"Authorization": f"Bearer {invitee_token}"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] == "fake-scoped-token"
    assert body["account_id"] == str(account.id)
    assert body["role"] == "member"

    membership = (
        db_session.query(AccountMember)
        .filter(AccountMember.account_id == account.id, AccountMember.user_id == invitee_id)
        .one()
    )
    assert membership.role == "member"

    db_session.refresh(invite)
    assert invite.accepted is True

    member_joined = [e for e in published_events if e["event_type"] == "member.joined"]
    assert len(member_joined) == 1
    assert member_joined[0]["payload"]["user_id"] == str(invitee_id)


def test_accept_invite_rejects_expired_invite(client, make_token, test_redis_client, db_session):
    owner_id = uuid.uuid4()
    account = _seed_account_with_owner(db_session, owner_id)
    invite, raw_token = _seed_invite(db_session, account.id, expired=True)

    token = make_token(jti="i6", sub=str(uuid.uuid4()))
    test_redis_client.setex("jti:i6", 900, "1")

    resp = client.post(f"/invites/{raw_token}/accept", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "invite_expired"


def test_accept_invite_rejects_already_used_invite(
    client, make_token, test_redis_client, db_session, fake_scoped_token,
):
    owner_id = uuid.uuid4()
    account = _seed_account_with_owner(db_session, owner_id)
    invite, raw_token = _seed_invite(db_session, account.id)

    first_invitee = uuid.uuid4()
    first_token = make_token(jti="i7", sub=str(first_invitee))
    test_redis_client.setex("jti:i7", 900, "1")
    client.post(f"/invites/{raw_token}/accept", headers={"Authorization": f"Bearer {first_token}"})

    second_invitee = uuid.uuid4()
    second_token = make_token(jti="i8", sub=str(second_invitee))
    test_redis_client.setex("jti:i8", 900, "1")
    resp = client.post(f"/invites/{raw_token}/accept", headers={"Authorization": f"Bearer {second_token}"})

    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "invite_already_used"


def test_accept_invite_rejects_existing_member(
    client, make_token, test_redis_client, db_session, fake_scoped_token,
):
    owner_id = uuid.uuid4()
    account = _seed_account_with_owner(db_session, owner_id)
    invite, raw_token = _seed_invite(db_session, account.id)

    # owner is already a member of this account — reuse their own invite token
    token = make_token(jti="i9", sub=str(owner_id))
    test_redis_client.setex("jti:i9", 900, "1")

    resp = client.post(f"/invites/{raw_token}/accept", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "already_a_member"


def test_accept_invite_rejects_unknown_token(client, make_token, test_redis_client):
    token = make_token(jti="i10", sub=str(uuid.uuid4()))
    test_redis_client.setex("jti:i10", 900, "1")

    resp = client.post("/invites/not-a-real-token/accept", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "invalid_invite"