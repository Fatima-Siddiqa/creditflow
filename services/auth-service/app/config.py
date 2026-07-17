from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://creditflow:creditflow@localhost:5433/creditflow"
    db_schema: str = "auth"

    redis_url: str = "redis://localhost:6380/1"

    rabbitmq_url: str = "amqp://guest:guest@localhost:5673/"

    jwt_private_key_path: str = "../../keys/jwt_private.pem"
    jwt_public_key_path: str = "../../keys/jwt_public.pem"
    jwt_algorithm: str = "RS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7

    login_rate_limit_max_attempts: int = 5
    login_rate_limit_window_seconds: int = 300

    # Shared secret gating POST /auth/issue-scoped-token. This endpoint mints
    # a JWT for a given (user_id, account_id, role) with no password check —
    # it trusts the caller to have already verified membership. Only
    # User/Tenant Service (Phase 4) should ever call it, service-to-service,
    # never the browser. Local default below is a placeholder; override via
    # .env for anything beyond solo local dev, same convention as the
    # Postgres/RabbitMQ defaults elsewhere in this file.
    internal_service_secret: str = "dev-only-internal-secret-change-me"
settings = Settings()