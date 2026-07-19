from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://creditflow:creditflow@localhost:5433/creditflow"
    db_schema: str = "usage"

    redis_url: str = "redis://localhost:6380/1"  # auth-service's jti store, read-only
    usage_redis_url: str = "redis://localhost:6380/4"  # this service's own live counters (index 4, see docs/CONVENTIONS.md)
    rabbitmq_url: str = "amqp://guest:guest@localhost:5673/"

    jwt_public_key_path: str = "../../keys/jwt_public.pem"
    jwt_algorithm: str = "RS256"

    # Flat per-account monthly quota, same for every plan tier. Spec §8
    # Service 6 requires quota enforcement but doesn't tie the limit to
    # plan_tier, and no other service currently exposes a per-plan token
    # limit for this service to look up (billing-service only knows
    # plan_tier/price, not a token allowance -- see the note in
    # app/events/ai_consumer.py). This is a documented simplification,
    # not a spec requirement -- revisit if/when a plan-tier-aware limit
    # is actually needed.
    default_monthly_token_quota: int = 100_000

    reconciliation_interval_seconds: int = 300

    # Shared secret gating cross-account reads of GET /usage/summary --
    # must match every other service's value (see .env.example).
    internal_service_secret: str = "dev-only-internal-secret-change-me"


settings = Settings()
