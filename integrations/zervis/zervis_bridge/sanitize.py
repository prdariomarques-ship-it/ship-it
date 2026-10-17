"""Fronteira de privacidade dos eventos: o que sai do Dario OS para o Zérvis.

Os payloads do Event Bus carregam PII (`phone`, `contact_id`, `job_payload`)
e, em `admin.*`, valores de configuração. O Zérvis pode repassá-los a um
provedor de LLM, então a regra é *deny by default*: só passa evento listado, e
só os campos listados dele. Estender é editar `_POLICY` e o teste (decisão de
revisão, não detalhe), como o allowlist de caminhos em `auth/scopes.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_MAX_STR = 200
_MAX_LIST = 20

# nome exato → campos; "dominio.*" cobre todo evento do domínio sem entrada exata.
_POLICY: dict[str, frozenset[str]] = {
    "job.*": frozenset({"job_id", "job_name", "attempts", "status", "detail"}),
    "goal.*": frozenset(
        {"goal_id", "title", "status", "priority", "progress_percent", "detail"}
    ),
    "agent.selected": frozenset({"agent"}),
    "agent.replied": frozenset(
        {"agent", "provider", "tool_calls", "duration_ms", "cost_usd"}
    ),
    "agent.failed": frozenset({"agent", "reason"}),
    "whatsapp.session_changed": frozenset({"provider", "status"}),
    "whatsapp.message_delivery_ack": frozenset({"provider", "status"}),
    # Só o fato: sem telefone, contato ou conteúdo.
    "whatsapp.message_received": frozenset({"provider"}),
    "observation.context_updated": frozenset(
        {"trigger", "item_count", "degraded_sources"}
    ),
}


def _fields_for(name: str) -> frozenset[str] | None:
    exact = _POLICY.get(name)
    if exact is not None:
        return exact
    domain = name.split(".", 1)[0]
    return _POLICY.get(f"{domain}.*")


def _clean(value: Any) -> Any:
    """Escalares e listas curtas de escalares; qualquer outra forma é descartada."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value[:_MAX_STR]
    if isinstance(value, list):
        return [
            _clean(item)
            for item in value[:_MAX_LIST]
            if isinstance(item, str | int | float | bool)
        ]
    raise TypeError(type(value).__name__)


def sanitize_event(raw: Any) -> dict[str, Any] | None:
    """Evento do bus (`{"name", "payload", "occurred_at"}`) → forma segura, ou None."""
    if not isinstance(raw, Mapping):
        return None
    name = raw.get("name")
    payload = raw.get("payload")
    occurred_at = raw.get("occurred_at")
    if not isinstance(name, str) or not isinstance(occurred_at, str):
        return None
    allowed = _fields_for(name)
    if allowed is None:
        return None
    safe: dict[str, Any] = {}
    if isinstance(payload, Mapping):
        for key in allowed:
            if key not in payload:
                continue
            try:
                safe[key] = _clean(payload[key])
            except TypeError:
                continue
    return {"name": name, "occurred_at": occurred_at[:40], "payload": safe}
