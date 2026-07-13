from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://creditflow:creditflow@localhost:5432/creditflow"
    db_schema: str = "auth"

    redis_url: str = "redis://localhost:6379/1"  # DB index 1, per CONVENTIONS.md

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    jwt_private_key_path: str = "../../keys/jwt_private.pem"
    jwt_public_key_path: str = "../../keys/jwt_public.pem"
    jwt_algorithm: str = "RS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7

    login_rate_limit_max_attempts: int = 5
    login_rate_limit_window_seconds: int = 300


settings = Settings()