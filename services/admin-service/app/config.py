from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://creditflow:creditflow@localhost:5433/creditflow"
    db_schema: str = "admin"

    redis_url: str = "redis://localhost:6380/1"       # this service's own state (none currently — reserved)
    auth_jti_redis_url: str = "redis://localhost:6380/1"  # read-only: auth-service's active jti store
    rabbitmq_url: str = "amqp://guest:guest@localhost:5673/"

    jwt_public_key_path: str = "../../keys/jwt_public.pem"
    jwt_algorithm: str = "RS256"

    internal_service_secret: str = "dev-only-internal-secret-change-me"
    user_service_url: str = "http://localhost:8002"
    credits_service_url: str = "http://localhost:8004"
    usage_service_url: str = "http://localhost:8005"


settings = Settings()