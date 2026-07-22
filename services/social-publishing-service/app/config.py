from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql://creditflow:creditflow@localhost:5433/creditflow"
    db_schema: str = "social"
    redis_url: str = "redis://localhost:6380/1"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5673/"
    jwt_public_key_path: str = "../../keys/jwt_public.pem"
    jwt_algorithm: str = "RS256"
    internal_service_secret: str = ""
    content_service_url: str = "http://localhost:8007"
    token_encryption_key: str = ""  # Fernet key, base64, from env -- never commit
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = "http://localhost:8000/api/social/linkedin/callback"

settings = Settings()