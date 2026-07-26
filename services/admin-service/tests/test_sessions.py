import fakeredis
from app.redis_client import auth_jti_redis_client as _c
from app.api import admin as admin_module

def test_revoke_session_removes_redis_key(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    fake.setex("jti:abc123", 3600, "1")
    monkeypatch.setattr(admin_module, "auth_jti_redis_client", fake)
    assert fake.exists("jti:abc123")
    admin_module.revoke_session("abc123", payload={"platform_role": "superadmin"})
    assert not fake.exists("jti:abc123")