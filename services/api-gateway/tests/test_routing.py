from app.config import settings
from app.routing import ROUTE_MAP, resolve_service_base_url


def test_route_map_covers_every_downstream_service_prefix():
    expected = {
        "auth", "accounts", "invites", "billing", "credits", "usage", "ai",
        "content", "scheduler", "social", "scraper", "notifications", "admin",
    }
    assert set(ROUTE_MAP.keys()) == expected


def test_accounts_and_invites_share_user_service():
    assert resolve_service_base_url("accounts") == resolve_service_base_url("invites") == settings.user_service_url


def test_resolve_known_prefix_returns_configured_url():
    assert resolve_service_base_url("auth") == settings.auth_service_url
    assert resolve_service_base_url("billing") == settings.billing_service_url


def test_resolve_unknown_prefix_returns_none():
    assert resolve_service_base_url("nonexistent") is None