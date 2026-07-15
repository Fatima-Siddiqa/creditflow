from app.config import settings
from app.routing import ROUTE_MAP, resolve_service_base_url


def test_route_map_covers_all_12_downstream_services():
    assert len(ROUTE_MAP) == 12


def test_resolve_known_prefix_returns_configured_url():
    assert resolve_service_base_url("auth") == settings.auth_service_url
    assert resolve_service_base_url("billing") == settings.billing_service_url


def test_resolve_unknown_prefix_returns_none():
    assert resolve_service_base_url("nonexistent") is None