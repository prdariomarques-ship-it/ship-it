"""Application settings loaded from environment variables (.env supported)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "Dario OS"
    app_version: str = "0.2.1"
    environment: str = "development"
    api_prefix: str = "/api"
    log_json: bool = False  # structured JSON logs (recommended in production)

    # Database
    database_url: str = "postgresql+asyncpg://dario:dario@localhost:5432/darioos"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Auth / JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    cache_default_ttl_seconds: int = 60

    # Rate limiting
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    # Qdrant (vector memory)
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "darioos_memory"
    embedding_dimensions: int = 1536
    contact_summary_every_n_messages: int = 10

    # LLM providers ("openai", "anthropic" or "glm")
    llm_provider: str = "openai"
    embedding_provider: str = "openai"  # Anthropic has no embeddings API; keep these separate

    openai_api_key: str = ""
    openai_base_url: str = ""  # override for OpenAI-compatible gateways
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    anthropic_max_tokens: int = 2048

    glm_api_key: str = ""
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    glm_model: str = "glm-4-plus"

    # Agents
    agent_max_iterations: int = 6

    # WhatsApp providers ("openwa", "baileys", "evolution" or "official")
    whatsapp_provider: str = "openwa"

    openwa_base_url: str = "http://localhost:8002"
    openwa_api_key: str = ""

    evolution_base_url: str = "http://localhost:8080"
    evolution_api_key: str = ""
    evolution_instance: str = "darioos"

    baileys_base_url: str = "http://localhost:3001"
    baileys_api_key: str = ""
    baileys_session: str = "darioos"

    official_api_base_url: str = "https://graph.facebook.com/v21.0"
    official_access_token: str = ""
    official_phone_number_id: str = ""

    # n8n
    n8n_base_url: str = "http://localhost:5678"

    # Inbound webhooks (when set, POST /webhooks/* requires X-Webhook-Token)
    webhook_secret: str = ""

    # Job queue
    jobs_enabled: bool = True
    jobs_poll_interval_seconds: float = 2.0
    jobs_default_max_attempts: int = 3
    jobs_retry_backoff_seconds: int = 30  # base for exponential backoff
    jobs_stale_after_seconds: int = 300  # running longer than this = crashed worker
    jobs_events_channel: str = "darioos:jobs:events"

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
