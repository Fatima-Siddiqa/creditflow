from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://creditflow:creditflow@localhost:5433/creditflow"
    db_schema: str = "ai"

    redis_url: str = "redis://localhost:6380/1"  # auth-service's jti store, read-only (verify_access_token, PR #2)

    # Index 3, shared with api-gateway (see docs/CONVENTIONS.md and
    # api-gateway/app/api/sse.py). This service PUBLISHes token chunks
    # and the [DONE]/[ERROR] <reason> sentinels here (app/sse_publisher.py,
    # PR #3); the gateway SUBSCRIBEs.
    sse_redis_url: str = "redis://localhost:6380/3"

    rabbitmq_url: str = "amqp://guest:guest@localhost:5673/"  # publisher only (PR #4) -- this service consumes no events

    jwt_public_key_path: str = "../../keys/jwt_public.pem"
    jwt_algorithm: str = "RS256"

    # ---- OpenRouter (PR #3) ----
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    fallback_models: list[str] = [
        "google/gemma-4-31b-it:free",
        "google/gemma-4-26b-a4b-it:free",
        "openai/gpt-oss-20b:free",
    ]

    # allowed_models: list[str] = ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"]
    # default_model: str = "openai/gpt-4o-mini"

    # ---- Cross-service calls (PR #2) ----
    usage_service_url: str = "http://localhost:8005"  # synchronous quota pre-check before accepting a generation request


settings = Settings()