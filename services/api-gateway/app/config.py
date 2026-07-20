from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # Read-only: auth-service's active-jti store (index 1, NOT the
    # gateway's own index 0). JWT verification (PR #4) needs to check
    # whether a token's jti is still active, and per CONVENTIONS.md this
    # store is meant to be read directly by other services (the Admin
    # Service does the same for its sessions view) rather than requiring
    # an HTTP round-trip to auth-service on every single proxied request.
    auth_jti_redis_url: str = "redis://localhost:6380/1"
    
    # Gateway owns Redis logical DB index 0 (rate-limit counters, webhook
    # dedup keys, SSE channel subscriptions) — see docs/CONVENTIONS.md.
    redis_url: str = "redis://localhost:6380/0"

    # Index 3, shared with ai-generation-service (Phase 8): SSE token
    # pub/sub fan-out. Gateway SUBSCRIBEs here, ai-generation-service
    # PUBLISHes here — they must agree on the index or messages are
    # silently dropped (Redis pub/sub never crosses logical DB indexes).
    # Kept separate from the gateway's own index-0 redis_url on purpose.
    sse_redis_url: str = "redis://localhost:6380/3"

    # Publisher-only: relays verified/deduped webhook events onto the
    # relevant domain exchanges. No queues bound here, no consuming.
    rabbitmq_url: str = "amqp://guest:guest@localhost:5673/"

    # Gateway never holds the private key — verification only.
    jwt_public_key_path: str = "../../keys/jwt_public.pem"
    jwt_algorithm: str = "RS256"

    # ---- Downstream service base URLs (static route map, PR #2) ----
    # Local/pytest defaults point at host-published ports; docker-compose's
    # environment: block overrides each to its container hostname:8000.
    # Port numbers follow spec §2's service table order (Auth=#2 -> 8001,
    # User/Tenant=#3 -> 8002, ... Admin=#13 -> 8012). Services not yet
    # built still get a real default here — requests to them 502 with
    # "service unreachable" until that phase lands, which is expected.
    auth_service_url: str = "http://localhost:8001"
    user_service_url: str = "http://localhost:8002"
    billing_service_url: str = "http://localhost:8003"
    credits_service_url: str = "http://localhost:8004"
    usage_service_url: str = "http://localhost:8005"
    ai_generation_service_url: str = "http://localhost:8006"
    content_service_url: str = "http://localhost:8007"
    scheduler_service_url: str = "http://localhost:8008"
    social_publishing_service_url: str = "http://localhost:8009"
    scraper_service_url: str = "http://localhost:8010"
    notification_service_url: str = "http://localhost:8011"
    admin_service_url: str = "http://localhost:8012"

    # ---- Rate limiting (PR #4) ----
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests_per_account: int = 100
    rate_limit_max_requests_per_ip: int = 200

    # ---- Webhooks (this phase) ----
    webhook_dedup_ttl_seconds: int = 86400  # 24h, per spec §8 Service 1
    stripe_webhook_secret: str = ""
    linkedin_webhook_secret: str = ""
    openrouter_webhook_secret: str = ""
    # LinkedIn/OpenRouter secrets are placeholders: as of this phase,
    # neither product has a confirmed real inbound-webhook mechanism for
    # what this project actually integrates with (LinkedIn's Sign-In/
    # Share products are outbound-only from our side; OpenRouter's
    # completions API is synchronous). Built anyway because spec §8
    # Service 1 lists all three endpoints with no hedge. See
    # docs/EVENT_CONTRACTS.md's "Webhook relay events" section.


settings = Settings()