"""Application settings loaded from environment variables (.env supported)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from utils.version_file import read_version_file

# VERSION.json is the release process's single source of truth (see
# RC1_AUDIT.md / RELEASE_NOTES.md) — app_version used to be a hardcoded
# literal here, drifting out of sync with the actual tagged release the
# moment a new one shipped (confirmed live: showed "0.2.1" while the repo
# was on v1.3.1). Reports "unknown" rather than a fabricated number when no
# VERSION.json exists (e.g. running from source without a release build).
_APP_VERSION_DEFAULT = read_version_file().get("version", "unknown")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Application
    app_name: str = "Dario OS"
    app_version: str = _APP_VERSION_DEFAULT
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
    password_reset_token_expire_minutes: int = 30
    # Tighter than the global HTTP rate limit (rate_limit_requests below) --
    # these two are keyed by email/IP specifically for the reset flow, not
    # the generic per-client-IP window every other route already gets.
    password_reset_request_limit: int = 5
    password_reset_request_window_seconds: int = 3600
    password_reset_confirm_limit: int = 10
    password_reset_confirm_window_seconds: int = 3600

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
    embedding_provider: str = (
        "openai"  # Anthropic has no embeddings API; keep these separate
    )
    # Automatic provider switch (AgentExecutor): when the primary LLM_PROVIDER
    # raises mid-run, retry once with this provider instead. Empty (default)
    # means no fallback — a provider exception propagates, same as before.
    llm_fallback_provider: str = ""

    # Per-call timeout for every LLM provider (openai/anthropic/gemini and
    # their subclasses glm/ollama). Without this, the openai/anthropic SDKs
    # default to a 600s read timeout — longer than jobs_execution_timeout_seconds
    # (240s), so the job-level timeout was the only thing bounding a slow call
    # in practice, with no way to tell "this LLM call was slow" apart from any
    # other cause of a job timing out. A tighter, provider-level timeout fails
    # with a specific, attributable error instead.
    llm_request_timeout_seconds: float = 60.0

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
    # openwa_base_url is the backend's internal Docker-network address
    # (e.g. http://openwa:8002) -- not reachable from Dário's browser. The
    # QR pairing page (see docker/openwa/Dockerfile) is only ever delivered
    # over that container's own WebSocket to its popup page, with no REST
    # equivalent (confirmed against the running gateway: "Cannot find
    # method: getQRCode"), so the dashboard links to the popup directly
    # instead of proxying it. Empty by default -- unset means no link is
    # shown, rather than guessing a host/IP that might be wrong.
    openwa_public_qr_url: str = ""

    # Google-backed providers (Gmail, Calendar, Contacts, Drive): retry with
    # exponential backoff for transient HTTP failures, same contract as
    # whatsapp_request_* above (see providers/google_http.py).
    google_request_max_attempts: int = 3
    google_request_backoff_seconds: float = 1.0

    evolution_base_url: str = "http://localhost:8080"
    evolution_api_key: str = ""
    evolution_instance: str = "darioos"

    baileys_base_url: str = "http://localhost:3001"
    baileys_api_key: str = ""
    baileys_session: str = "darioos"

    official_api_base_url: str = "https://graph.facebook.com/v22.0"
    official_access_token: str = ""
    official_phone_number_id: str = ""
    official_app_secret: str = (
        ""  # signs webhooks (X-Hub-Signature-256); optional but recommended
    )
    # Echoed back by GET /webhooks/whatsapp during Meta's webhook subscription
    # handshake (hub.mode=subscribe&hub.verify_token=...&hub.challenge=...).
    # Set to any secret string of your choosing and enter the same value in
    # the Meta App Dashboard's webhook config.
    official_webhook_verify_token: str = ""

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
    # Must stay below jobs_stale_after_seconds: a handler that runs past this
    # is cancelled and fails cleanly through the normal retry path, so it
    # always leaves RUNNING on its own — the stale-job recovery below never
    # gets a chance to also reclaim it and run it a second time concurrently
    # (see JobWorker.__init__'s assertion of this invariant).
    jobs_execution_timeout_seconds: int = 240
    jobs_max_concurrent_workers: int = 5  # max jobs executing concurrently per worker

    # Event Bus (best-effort Redis fan-out; in-process delivery never depends on it)
    events_channel: str = "darioos:events"

    # Context Observation Engine (observation/) — keeps a CurrentContext
    # snapshot fresh via a self-rescheduling job (jobs/), not a new timer
    # primitive; see docs/OBSERVATION_ENGINE.md.
    observation_enabled: bool = True
    observation_interval_seconds: float = 300.0  # re-observe even with no triggering event
    observation_context_limit: int = 5  # items per dimension; matches orchestrator.context._OWNER_CONTEXT_LIMIT

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
    google_calendar_redirect_uri: str = (
        ""  # e.g. https://<domain>/api/gcalendar/oauth/callback
    )
    google_calendar_api_base_url: str = "https://www.googleapis.com/calendar/v3"

    # Google Contacts (People API, Sprint 2) — same reuse pattern as Calendar above.
    contacts_provider: str = "google"
    google_contacts_redirect_uri: str = (
        ""  # e.g. https://<domain>/api/gcontacts/oauth/callback
    )
    google_people_api_base_url: str = "https://people.googleapis.com/v1"

    # Contact Workspace (Release 1.5, P0-2) -- combined-timeline cap, not a
    # storage limit; a business value on purpose, so it's here rather than
    # hardcoded in api/contact_workspace.py.
    contact_workspace_timeline_limit: int = 30

    # Google Drive (Sprint 3) — base de conhecimento; mesmo padrão de reuso de
    # google_client_id/google_client_secret/email_token_encryption_key.
    drive_provider: str = "google"
    google_drive_redirect_uri: str = (
        ""  # e.g. https://<domain>/api/gdrive/oauth/callback
    )
    google_drive_api_base_url: str = "https://www.googleapis.com/drive/v3"
    # Trava de segurança de "download seguro": arquivo maior que isto é
    # recusado antes de baixar, nunca lido parcialmente na memória.
    gdrive_max_file_size_bytes: int = 20_000_000

    # OpenTelemetry tracing (Sprint 5) — off by default; no collector exists
    # in every environment this runs in. When enabled with no endpoint set,
    # spans print to stdout (console exporter) instead of failing to export.
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = ""
    otel_sampling: str = (
        ""  # "always", "never", "fixed:0.1", "parent-fixed:0.1", "error:0.05", etc.
    )
    otel_prometheus_metrics: bool = (
        False  # Enable Prometheus metrics reader for tracing
    )

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost"

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
