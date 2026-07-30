from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://creditflow:creditflow@localhost:5433/creditflow"
    db_schema: str = "notification"

    redis_url: str = "redis://localhost:6380/1"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5673/"

    email_provider_api_key: str = "dev-only-mailgun-key"
    email_from_address: str = "postmaster@sandbox3d5f0101e250427baea0a712f04860f4.mailgun.org"  # your actual sandbox domain
    email_provider_base_url: str = "https://api.mailgun.net/v3"
    email_provider_domain: str = "sandbox3d5f0101e250427baea0a712f04860f4.mailgun.org"  # NEW — Mailgun needs this in the URL path
    frontend_origin: str = "http://localhost:5173" 
    slack_webhook_url: str = ""

    internal_service_secret: str = "dev-only-internal-secret-change-me"
    auth_service_url: str = "http://localhost:8001"
    user_service_url: str = "http://localhost:8002"


settings = Settings()