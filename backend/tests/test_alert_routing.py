"""Alerta ao dono (Gêmeo/anti-loop) sai por outra linha quando a da loja está fora do ar. Worker e handler REAIS; só o transporte é simulado."""
import pytest

from jobs.service import JobService
from jobs.worker import JobWorker
from providers.whatsapp.evolution.provider import EvolutionProvider
from services import line_watch
from tests.test_whatsapp_send_queue_retry import PHONE, control_db  # noqa: F401 -- fixture (migrações das tabelas de controle)
from utils.config import get_settings


class _Evolution(EvolutionProvider):
    def __init__(self):
        super().__init__()
        self.calls: list[tuple] = []

    async def send_text(self, to, content, instance=None):
        self.calls.append((to, content, instance))
        return {"key": {"id": f"EVT-{len(self.calls)}"}}


@pytest.fixture
def transport(monkeypatch):
    fake = _Evolution()
    monkeypatch.setattr("jobs.handlers.get_whatsapp_provider", lambda: fake)

    async def no_memory(*a, **k):
        return False
    monkeypatch.setattr("services.messaging.contact_memory_service.record_interaction", no_memory)
    s = get_settings()
    monkeypatch.setattr(s, "evolution_instance", "MARQUESCOLOR")
    monkeypatch.setattr(s, "evolution_personal_instance", "Dario")
    line_watch.line_watch_state.reset()
    yield fake
    line_watch.line_watch_state.reset()


async def _send(sessions, extra):
    async with sessions() as db:
        if extra.get("_twin_alert_dedup_key"):                                               # a reserva que decide_owner_alert faz antes de enfileirar
            from services import conversation_control
            await conversation_control.alert_claim(db, extra["_twin_alert_contact_id"], extra["_twin_alert_instance"], extra["_twin_alert_dedup_key"])
            await db.commit()
        await JobService(db).enqueue("whatsapp.send_text", {"to": PHONE, "content": "[Gêmeo Darius] Mensagem sensível não respondida.", **extra})
    await JobWorker().run_once()


ALERT = {"_twin_alert_contact_id": 1, "_twin_alert_dedup_key": "dedup-1", "_twin_alert_instance": "Dario"}


@pytest.mark.asyncio
async def test_owner_alert_goes_through_another_open_line_when_the_store_line_is_down(control_db, transport):
    line_watch.record_states({"MARQUESCOLOR": "connecting", "b2b-sales": "open", "Dario": "open"})
    await _send(control_db, ALERT)
    assert [c[2] for c in transport.calls] == ["b2b-sales"]


@pytest.mark.asyncio
async def test_owner_alert_keeps_the_default_line_when_the_store_is_up_or_unknown(control_db, transport):
    await _send(control_db, ALERT)                                                          # sem leitura do vigia
    line_watch.record_states({"MARQUESCOLOR": "open", "b2b-sales": "open"})
    await _send(control_db, {**ALERT, "_twin_alert_dedup_key": "dedup-2"})                  # loja no ar
    assert [c[2] for c in transport.calls] == [None, None]


@pytest.mark.asyncio
async def test_non_alert_sends_and_explicit_instances_are_never_rerouted(control_db, transport):
    line_watch.record_states({"MARQUESCOLOR": "connecting", "b2b-sales": "open"})
    await _send(control_db, {})                                                              # envio comum, sem instância
    await _send(control_db, {"instance": "azusa-church"})                                    # instância explícita
    assert [c[2] for c in transport.calls] == [None, "azusa-church"]
