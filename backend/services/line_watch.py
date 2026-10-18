"""Vigia das linhas do WhatsApp: consulta `GET /instance/connectionState/<instancia>` no Evolution e decide quando avisar o dono.

Motivo: em 16/10/2026 a linha da loja caiu (`device_removed`, estado `connecting`) e ficou ~12 h fora sem ninguem perceber; nenhuma regra do
Prometheus cobria isso. Este modulo e ADITIVO: nao toca no provedor do WhatsApp nem no fluxo das mensagens. So le o estado e, quando
preciso, enfileira um `whatsapp.send_text` para o dono por uma linha que esteja `open` (preferindo uma que nao seja a pessoal).

Regras: so avisa depois de `confirm_checks` rodadas seguidas fora do ar; nao repete antes de `repeat_minutes`; avisa uma vez quando volta.
Se NENHUMA linha esta no ar (ou o Evolution nao responde), nao ha por onde avisar: so registra no log.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

from services.rate_limit import rate_limiter

OPEN = "open"
UNREACHABLE = "unreachable"


@dataclass
class LineEvent:
    kind: str          # "down" | "still_down" | "recovered"
    instance: str
    state: str
    checks_down: int = 0


@dataclass
class LineWatchState:
    bad_checks: dict[str, int] = field(default_factory=dict)
    alerted: set[str] = field(default_factory=set)

    def reset(self) -> None:
        self.bad_checks.clear()
        self.alerted.clear()


line_watch_state = LineWatchState()


def watched_instances(settings) -> list[str]:
    names = [n.strip() for n in settings.line_watch_instances.split(",") if n.strip()]
    if not names:
        names = [n for n in (settings.evolution_instance, settings.evolution_personal_instance) if n]
    return list(dict.fromkeys(names))


async def fetch_states(instances: list[str], *, base_url: str, api_key: str, timeout: float = 15.0,
                       transport: httpx.AsyncBaseTransport | None = None) -> dict[str, str]:
    """Estado de cada instancia segundo o Evolution; erro de rede/HTTP vira `unreachable` (nunca levanta)."""
    states: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        for instance in instances:
            try:
                response = await client.get(f"{base_url.rstrip('/')}/instance/connectionState/{quote(instance, safe='')}",
                                            headers={"apikey": api_key})
                if response.status_code != 200:
                    states[instance] = UNREACHABLE
                    continue
                state = (response.json().get("instance") or {}).get("state")
                states[instance] = str(state) if state else UNREACHABLE
            except (httpx.HTTPError, ValueError, AttributeError):
                states[instance] = UNREACHABLE
    return states


async def evaluate(states: dict[str, str], *, confirm_checks: int, repeat_minutes: int,
                   state: LineWatchState = line_watch_state) -> list[LineEvent]:
    """Atualiza o estado em memoria e devolve os avisos devidos nesta rodada."""
    events: list[LineEvent] = []
    for instance, current in states.items():
        if current == OPEN:
            state.bad_checks[instance] = 0
            if instance in state.alerted:
                state.alerted.discard(instance)
                events.append(LineEvent("recovered", instance, current))
            continue
        bad = state.bad_checks.get(instance, 0) + 1
        state.bad_checks[instance] = bad
        if bad < max(1, confirm_checks):
            continue
        # O limitador (Redis, com fallback local) segura repeticoes mesmo se o backend reiniciar no meio da queda.
        allowed = await rate_limiter.is_allowed(f"line-watch:{instance}", limit=1, window_seconds=max(60, repeat_minutes * 60))
        first = instance not in state.alerted
        state.alerted.add(instance)
        if allowed:
            events.append(LineEvent("down" if first else "still_down", instance, current, bad))
    return events


def pick_sender(states: dict[str, str], down_instance: str, personal_instance: str = "") -> str | None:
    """Uma linha no ar (diferente da que caiu), preferindo uma que NAO seja a pessoal do dono."""
    open_lines = [i for i, s in states.items() if s == OPEN and i != down_instance]
    others = [i for i in open_lines if i != personal_instance]
    return (others or open_lines or [None])[0]


def message_for(event: LineEvent, interval_seconds: int) -> str:
    if event.kind == "recovered":
        return f"✅ A linha {event.instance} voltou (open). Alerta automático, não responda."
    minutes = max(1, round(event.checks_down * interval_seconds / 60))
    again = " (lembrete)" if event.kind == "still_down" else ""
    return (f"⚠️ A linha {event.instance} está FORA DO AR{again}: estado \"{event.state}\" há cerca de {minutes} min. "
            "Veja o aparelho (Aparelhos conectados) e o QR no painel do Evolution. Alerta automático, não responda.")
