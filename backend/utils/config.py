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
    # Automatic provider switch (AgentExecutor): when the primary LLM_PROVIDER
    # raises mid-run, retry once with this provider instead. Empty (default)
    # means no fallback — a provider exception propagates, same as before.
    llm_fallback_provider: str = ""

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

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3.1"

    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-2.0-flash"
    gemini_embedding_model: str = "text-embedding-004"

    # Agents
    agent_max_iterations: int = 6
    agent_run_timeout_seconds: int = 60

    # WhatsApp providers ("openwa", "baileys", "evolution" or "official")
    whatsapp_provider: str = "openwa"
    # Shared by every provider (base._request): retry with exponential
    # backoff for transient HTTP failures (network blips, 5xx from gateway).
    whatsapp_request_max_attempts: int = 3
    whatsapp_request_backoff_seconds: float = 1.0

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
    official_app_secret: str = ""  # signs webhooks (X-Hub-Signature-256); optional but recommended

    # n8n
    n8n_base_url: str = "http://localhost:5678"

    # Inbound webhooks (when set, POST /webhooks/* requires X-Webhook-Token)
    webhook_secret: str = ""

    # Automatic end-to-end reply: webhook -> AI Orchestrator -> send.
    # Disable if an external automation (e.g. n8n) should own replies instead,
    # to avoid the contact receiving two answers to the same message.
    auto_reply_enabled: bool = True
    # Loop/flood breaker: max automatic replies per contact per minute.
    auto_reply_max_per_contact_per_minute: int = 6

    # Job queue
    jobs_enabled: bool = True
    jobs_poll_interval_seconds: float = 2.0
    jobs_default_max_attempts: int = 3
    jobs_retry_backoff_seconds: int = 30  # base for exponential backoff
    jobs_stale_after_seconds: int = 300  # running longer than this = crashed worker

    # Event Bus (best-effort Redis fan-out; in-process delivery never depends on it)
    events_channel: str = "darioos:events"

    # Mail (Gmail) — a domain independent of WhatsApp/Loja/Igreja/Investimentos/Agenda.
    # Optional: unset means the Gmail integration simply isn't available (no boot
    # failure) — only /api/mail/connect requires all three to be configured.
    mail_provider: str = "gmail"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""  # e.g. https://<domain>/api/mail/oauth/callback
    # Symmetric key (Fernet, urlsafe-base64, 32 bytes) — encrypts every Google
    # OAuth refresh token at rest (Gmail, Calendar, Contacts all share it: same
    # kind of secret, same trust boundary, no reason for three separate keys).
    # generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    email_token_encryption_key: str = ""
    gmail_api_base_url: str = "https://gmail.googleapis.com"
    google_oauth_base_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"

    # Google Calendar (Sprint 2) — reuses google_client_id/google_client_secret
    # above (same OAuth app as Gmail; just register this redirect URI too in
    # Google Cloud Console) and email_token_encryption_key for token storage.
    # Its own domain, own connection, own opt-in — same shape as Gmail.
    calendar_provider: str = "google"
    google_calendar_redirect_uri: str = ""  # e.g. https://<domain>/api/gcalendar/oauth/callback
    google_calendar_api_base_url: str = "https://www.googleapis.com/calendar/v3"

    # Google Contacts (People API, Sprint 2) — same reuse pattern as Calendar above.
    contacts_provider: str = "google"
    google_contacts_redirect_uri: str = ""  # e.g. https://<domain>/api/gcontacts/oauth/callback
    google_people_api_base_url: str = "https://people.googleapis.com/v1"

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
