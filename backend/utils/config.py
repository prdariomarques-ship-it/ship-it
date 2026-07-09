"""Application settings loaded from environment variables (.env supported)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "Dario OS"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True
    api_prefix: str = "/api"

    # Database
    database_url: str = "postgresql+asyncpg://dario:dario@localhost:5432/darioos"

    # Auth / JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Rate limiting
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    # Qdrant (vector memory)
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "darioos_memory"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # n8n
    n8n_base_url: str = "http://localhost:5678"
    n8n_webhook_path: str = "/webhook/darioos"

    # OpenWA (WhatsApp)
    openwa_base_url: str = "http://localhost:8002"
    openwa_api_key: str = ""

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
