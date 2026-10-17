"""Configuração por variáveis de ambiente (prefixo `ZERVIS_BRIDGE_`)."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ZERVIS_BRIDGE_", extra="ignore")

    # Dario OS (REST, token com escopo de leitura emitido por mint_scoped_token.py).
    darioos_api_url: str = "http://backend:8000/api"
    darioos_token: SecretStr
    request_timeout_seconds: float = 15.0
    request_max_attempts: int = Field(default=3, ge=1, le=6)
    request_backoff_seconds: float = Field(default=0.5, ge=0)

    # Event Bus (Redis pub/sub, mesmo canal de `events_channel` no backend).
    redis_url: str = "redis://redis:6379/0"
    events_channel: str = "darioos:events"
    subscriber_backoff_max_seconds: float = 30.0

    # Buffer de eventos servido por `eventos_recentes`.
    buffer_max_events: int = Field(default=500, ge=1, le=10_000)
    buffer_ttl_seconds: float = Field(default=3600.0, gt=0)

    # Servidor MCP (HTTP). Credencial distinta do token do Dario OS: quem fala
    # com a ponte não recebe, por isso, o token que a ponte usa.
    mcp_token: SecretStr
    host: str = "0.0.0.0"  # noqa: S104 - escopo de rede é do compose (bind em 127.0.0.1)
    port: int = 8810
    # Cabeçalhos Host aceitos (proteção contra DNS rebinding do SDK MCP).
    allowed_hosts: list[str] = ["localhost:*", "127.0.0.1:*", "zervis-bridge:*"]

    @field_validator("darioos_token", "mcp_token")
    @classmethod
    def _not_blank(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().strip()) < 16:
            raise ValueError("segredo ausente ou curto demais (mínimo 16 caracteres)")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # campos obrigatórios vêm do ambiente
