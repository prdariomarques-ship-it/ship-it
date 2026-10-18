"""Guarda de atividade do dono para os agentes que respondem CLIENTES (loja, B2B, Azusa).

Regra (a MESMA do Gemeo em `orchestrator/twin_policy.py::_is_owner_turn`): "dono ativo" = existe, no mesmo contato e na mesma linha, uma
mensagem de SAIDA com `sent_by_human=True` e sem ser resposta do autopilot, dentro da janela. Nao exige texto: audio, PDF, imagem e
video enviados por ele contam. Assinaturas na tabela `messages`: dono = sent_by_human=t, is_autopilot_reply=f; Gemeo = is_autopilot_reply=t;
outros agentes = sent_by_human=f, is_autopilot_reply=f.
Atencao: respostas automaticas do WhatsApp Business (ausencia/saudacao) tambem saem com sent_by_human=t e contariam como atividade do dono
(no Gemeo ja e assim hoje); o dono as removeu no aplicativo. Se voltarem, o agente fica calado ate a janela passar.

Duas verificacoes: `pre_check` (antes de gerar a resposta: evita o custo e os efeitos colaterais) e `send_guard` (imediatamente ANTES de
transmitir, pega o dono que entrou durante a geracao). Ao suprimir registra o evento `suppressed_owner_active` com agente, contato,
id da mensagem do dono, janela e fase. Janela por agente em /app/owner_activity_windows.txt (lido a cada decisao; sem reiniciar):
linhas `b2b=360`, `azusa=360`, `store=360`, `default=360`, em segundos; 0 desliga para aquele agente; `#` comenta.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

DEFAULT_WINDOW_SECONDS = 360
WINDOWS_FILE = os.environ.get("OWNER_ACTIVITY_FILE", "/app/owner_activity_windows.txt")
_ALIASES = {"azusa_intake": "azusa", "b2b-sales": "b2b", "azusa-church": "azusa", "loja": "store"}


@dataclass(frozen=True)
class OwnerActivity:
    message_id: int
    at: datetime
    media_type: str


def load_windows(path: str | None = None) -> dict[str, int]:
    """{'default': 360, 'b2b': 120, ...}; arquivo ausente/ilegivel = {} (tudo no padrao). Linhas invalidas sao ignoradas."""
    out: dict[str, int] = {}
    try:
        with open(path or WINDOWS_FILE, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return out
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        key, sep, value = line.replace(":", "=").partition("=")
        key, value = key.strip().lower(), value.strip()
        if sep and key and value.isdigit():
            out[_ALIASES.get(key, key)] = int(value)
    return out


def window_for(agent: str, windows: dict[str, int] | None = None) -> int:
    windows = load_windows() if windows is None else windows
    name = _ALIASES.get(agent.lower(), agent.lower())
    return windows.get(name, windows.get("default", DEFAULT_WINDOW_SECONDS))


def _val(x) -> str:
    return str(getattr(x, "value", x)).lower()


def _stamp(row) -> datetime | None:
    for name in ("provider_timestamp", "created_at"):          # um epoch (int) ou None nao pode desligar a guarda
        cand = getattr(row, name, None)
        if isinstance(cand, datetime):
            return cand if cand.tzinfo else cand.replace(tzinfo=timezone.utc)
    return None


def is_owner_turn(row) -> bool:
    return (_val(row.direction) == "outbound" and bool(getattr(row, "sent_by_human", False))
            and not bool(getattr(row, "is_autopilot_reply", False)))


def latest_owner_activity(rows, window_seconds: int, now: datetime | None = None) -> OwnerActivity | None:
    """Pura: a atividade do dono mais recente dentro da janela, ou None."""
    if window_seconds <= 0:
        return None
    now = now or datetime.now(timezone.utc)
    best: OwnerActivity | None = None
    for row in rows:
        if not is_owner_turn(row):
            continue
        at = _stamp(row)
        if at is None or (now - at).total_seconds() > window_seconds:     # relogio do provedor adiantado (at > now) conta como ativo
            continue
        if best is None or at > best.at:
            best = OwnerActivity(int(row.id), at, _val(getattr(row, "media_type", "text")))
    return best


async def find_owner_activity(db, contact_id: int, instance: str, window_seconds: int, now: datetime | None = None) -> OwnerActivity | None:
    if window_seconds <= 0:
        return None
    from repositories.message import MessageRepository

    rows = await MessageRepository(db).recent_for_contact(contact_id, limit=20, instance=instance or None)
    return latest_owner_activity(rows, window_seconds, now)


async def _suppressed(db, agent: str, contact_id: int, activity: OwnerActivity, window: int, phase: str, instance: str) -> None:
    from services.audit import record_log

    await record_log(
        db, source="owner_activity_guard", level="info", message="suppressed_owner_active",
        payload={"event": "suppressed_owner_active", "agent": agent, "contact_id": contact_id, "instance": instance,
                 "owner_message_id": activity.message_id, "owner_media": activity.media_type, "window_seconds": window, "phase": phase},
    )


async def pre_check(db, agent: str, contact_id: int, message_id: int, instance: str, now: datetime | None = None) -> bool:
    """True = o agente pode gerar a resposta; False = o dono esta ativo (registrado e suprimido)."""
    window = window_for(agent)
    activity = await find_owner_activity(db, contact_id, instance, window, now)
    if activity is None:
        return True
    await _suppressed(db, agent, contact_id, activity, window, "pre", instance)
    return False


def guard_payload(agent: str, contact_id: int, message_id: int) -> dict:
    """Marca o job de envio para a revalidacao imediatamente antes do transporte (`send_guard`)."""
    return {"_owner_guard": agent, "_owner_guard_contact_id": contact_id, "_owner_guard_message_id": message_id}


async def send_guard(db, payload: dict, instance: str | None, now: datetime | None = None) -> bool:
    """True = pode transmitir. So atua em envios marcados por `guard_payload`; qualquer outro envio passa sem custo."""
    agent = payload.get("_owner_guard")
    if not agent:
        return True
    contact_id = int(payload["_owner_guard_contact_id"])
    window = window_for(str(agent))
    activity = await find_owner_activity(db, contact_id, instance or "", window, now)
    if activity is None:
        return True
    await _suppressed(db, str(agent), contact_id, activity, window, "send", instance or "")
    return False
