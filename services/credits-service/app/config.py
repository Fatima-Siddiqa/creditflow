from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://creditflow:creditflow@localhost:5433/creditflow"
    db_schema: str = "credits"

    redis_url: str = "redis://localhost:6380/1"  # jti store, read-only
    rabbitmq_url: str = "amqp://guest:guest@localhost:5673/"

    jwt_public_key_path: str = "../../keys/jwt_public.pem"
    jwt_algorithm: str = "RS256"

    stripe_secret_key: str = "sk_test_dev_placeholder"
    stripe_price_id_pro: str = "price_dev_pro_placeholder"
    stripe_price_id_team: str = "price_dev_team_placeholder"

    dunning_grace_period_days: int = 7
    dunning_check_interval_seconds: int = 60
    outbox_poll_interval_seconds: float = 1.0


settings = Settings()