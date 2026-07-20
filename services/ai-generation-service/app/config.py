from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://creditflow:creditflow@localhost:5433/creditflow"
    db_schema: str = "ai"

    redis_url: str = "redis://localhost:6380/1"  # auth-service's jti store, read-only (verify_access_token, PR #2)

    # Index 3, shared with api-gateway (see docs/CONVENTIONS.md and
    # api-gateway/app/api/sse.py). This service PUBLISHes token chunks
    # and the [DONE]/[ERROR] <reason> sentinels here; the gateway
    # SUBSCRIBEs. Not used until PR #3 (streaming), declared now so
    # config.py doesn't need a second PR just to add one field.
    sse_redis_url: str = "redis://localhost:6380/3"

    rabbitmq_url: str = "amqp://guest:guest@localhost:5673/"  # publisher only (PR #4) -- this service consumes no events

    jwt_public_key_path: str = "../../keys/jwt_public.pem"
    jwt_algorithm: str = "RS256"

    # ---- OpenRouter (PR #3) ----
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Spec §8 Service 7: "Support at least 2 model choices via OpenRouter
    # (e.g. one fast/cheap, one higher quality) selectable by the user."
    # Allow-list, not a free-text field on the request -- PR #2 validates
    # the requested model against this before creating a generation_jobs
    # row, same spirit as usage-service's default_monthly_token_quota
    # being a flat, documented placeholder rather than a per-plan lookup
    # nothing upstream exposes yet.
    allowed_models: list[str] = ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"]
    default_model: str = "openai/gpt-4o-mini"

    # ---- Cross-service calls (PR #2) ----
    usage_service_url: str = "http://localhost:8005"  # synchronous quota pre-check before accepting a generation request


settings = Settings()