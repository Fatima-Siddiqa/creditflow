import pytest
from fastapi import HTTPException
from app.dependencies import require_admin_access

def test_superadmin_any_account():
    require_admin_access("some-account", {"platform_role": "superadmin"})  # no raise

def test_tenant_admin_own_account_only():
    require_admin_access("acc-1", {"account_id": "acc-1", "role": "owner"})  # no raise
    with pytest.raises(HTTPException) as e:
        require_admin_access("acc-2", {"account_id": "acc-1", "role": "owner"})
    assert e.value.status_code == 403