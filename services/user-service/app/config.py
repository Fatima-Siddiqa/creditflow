from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://creditflow:creditflow@localhost:5433/creditflow"
    db_schema: str = "tenant"

    # Index 1 — the SAME store auth-service writes jti keys into, not a
    # separate index. user-service only ever reads it (checking whether an
    # incoming token's jti is still an active session), identical pattern
    # to api-gateway's auth_jti_redis_client. Wired here now even though
    # PR #1 has no JWT-verifying endpoints yet — PR #3 will use it.
    redis_url: str = "redis://localhost:6380/1"

    rabbitmq_url: str = "amqp://guest:guest@localhost:5673/"

    # Verification only — this service never signs a token itself. Scoped-
    # token issuance is delegated to auth-service (PR #4).
    jwt_public_key_path: str = "../../keys/jwt_public.pem"
    jwt_algorithm: str = "RS256"

    # Gates the outbound call to POST /auth/issue-scoped-token (PR #4).
    # Must match auth-service's own internal_service_secret — see
    # docs/ARCHITECTURE.md "Internal cross-service calls".
    internal_service_secret: str = "dev-only-internal-secret-change-me"
    auth_service_url: str = "http://localhost:8001"


settings = Settings()