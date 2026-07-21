from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql://creditflow:creditflow@localhost:5433/creditflow"
    db_schema: str = "content"
    redis_url: str = "redis://localhost:6380/1"       # auth jti store, read-only
    rabbitmq_url: str = "amqp://guest:guest@localhost:5673/"
    jwt_public_key_path: str = "../../keys/jwt_public.pem"
    jwt_algorithm: str = "RS256"
    upload_dir: str = "/app/uploads"                  # local volume; swap for S3 in AWS bonus

settings = Settings()