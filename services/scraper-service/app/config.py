from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mongo_url: str = "mongodb://localhost:27018"
    mongo_db_name: str = "scraper"
    redis_url: str = "redis://localhost:6380/1"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5673/"
    jwt_public_key_path: str = "../../keys/jwt_public.pem"
    jwt_algorithm: str = "RS256"
    internal_service_secret: str = ""
    domain_rate_limit_seconds: int = 5
    recurring_scan_interval_seconds: int = 60

settings = Settings()