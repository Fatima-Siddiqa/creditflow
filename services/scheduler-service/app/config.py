from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql://creditflow:creditflow@localhost:5433/creditflow"
    db_schema: str = "scheduler"
    redis_url: str = "redis://localhost:6380/1"  # auth jti store, read-only
    # Celery broker/backend + double-fire lock. Index 2, per CONVENTIONS.md.
    celery_redis_url: str = "redis://localhost:6380/2"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5673/"
    jwt_public_key_path: str = "../../keys/jwt_public.pem"
    jwt_algorithm: str = "RS256"
    content_service_url: str = "http://localhost:8007"
    beat_interval_seconds: int = 60
    schedule_lookahead_days: int = 90  # calendar view cap, not a generation limit


settings = Settings()
