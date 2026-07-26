from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://creditflow:creditflow@localhost:5433/creditflow"
    db_schema: str = "notification"

    redis_url: str = "redis://localhost:6380/1"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5673/"

    email_provider_api_key: str = "dev-only-resend-key"
    email_from_address: str = "onboarding@resend.dev"
    email_provider_base_url: str = "https://api.resend.com"

    slack_webhook_url: str = ""

    internal_service_secret: str = "dev-only-internal-secret-change-me"
    auth_service_url: str = "http://localhost:8001"
    user_service_url: str = "http://localhost:8002"


settings = Settings()