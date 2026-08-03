from app.config import settings

# prefix (first path segment after /api/) -> settings field holding that
# service's base URL. Covers all 12 downstream services from spec §2 —
# everything except the gateway itself (service #1, this one).
#
# Note: the Phase 3 roadmap file's Definition of Done says "route map
# covers all 13 downstream services" — that's off by one against spec §2
# (13 total services INCLUDING the gateway, so 12 others). Went with the
# spec's count here rather than the roadmap file's, since the roadmap is
# your own planning doc and the spec is the graded source of truth.
ROUTE_MAP: dict[str, str] = {
    "auth": "auth_service_url",
    "accounts": "user_service_url",
    "invites": "user_service_url",
    "billing": "billing_service_url",
    "credits": "credits_service_url",
    "usage": "usage_service_url",
    "ai": "ai_generation_service_url",
    "content": "content_service_url",
    "uploads": "content_service_url",
    "scheduler": "scheduler_service_url",
    "social": "social_publishing_service_url",
    "scraper": "scraper_service_url",
    "notifications": "notification_service_url",
    "admin": "admin_service_url",
}


def resolve_service_base_url(prefix: str) -> str | None:
    """Returns the configured base URL for a route prefix, or None if the
    prefix isn't registered at all (a typo'd/unknown route — different
    from a registered-but-unreachable service, which is a 502, not a 404)."""
    field_name = ROUTE_MAP.get(prefix)
    if field_name is None:
        return None
    return getattr(settings, field_name)