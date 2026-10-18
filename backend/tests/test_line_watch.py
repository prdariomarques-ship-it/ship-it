"""Vigia das linhas (services/line_watch.py + jobs/line_watch_job.py). Evolution simulado (httpx.MockTransport); NÃO fala com o Evolution real."""
import json

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from jobs.line_watch_job import JOB_NAME, line_watch_tick, start
from jobs.service import JobService
from models.job import Job
from models.log import LogEntry
from repositories.job import JobRepository
from services import line_watch
from services.line_watch import LineEvent, LineWatchState
from utils.config import get_settings


@pytest.fixture(autouse=True)
def _fresh_state():
    line_watch.line_watch_state.reset()
    yield
    line_watch.line_watch_state.reset()


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    for name, value in dict(line_watch_enabled=True, line_watch_instances="MARQUESCOLOR,b2b-sales,azusa-church,Dario",
                            line_watch_interval_seconds=120, line_watch_confirm_checks=2, line_watch_repeat_minutes=60,
                            line_watch_alert_phone="5511999990000", whatsapp_owner_alert_phone="",
                            evolution_personal_instance="Dario").items():
        monkeypatch.setattr(s, name, value)
    return s


def _transport(states: dict[str, object]):
    def handler(request: httpx.Request) -> httpx.Response:
        instance = request.url.path.rsplit("/", 1)[-1]
        from urllib.parse import unquote
        value = states.get(unquote(instance))
        if isinstance(value, Exception):
            raise value
        if value is None:
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json={"instance": {"instanceName": instance, "state": value}})
    return httpx.MockTransport(handler)


async def test_fetch_states_maps_states_and_errors():
    states = await line_watch.fetch_states(
        ["a", "b", "c", "Dário Marques Neto"], base_url="http://evo", api_key="k",
        transport=_transport({"a": "open", "b": "connecting", "c": httpx.ConnectError("x"), "Dário Marques Neto": "open"}))
    assert states == {"a": "open", "b": "connecting", "c": "unreachable", "Dário Marques Neto": "open"}
    assert (await line_watch.fetch_states(["x"], base_url="http://evo", api_key="k", transport=_transport({})))["x"] == "unreachable"


async def test_sends_apikey_header_and_never_raises():
    seen = {}

    def handler(request):
        seen["key"] = request.headers["apikey"]
        return httpx.Response(200, text="isso nao e json")
    out = await line_watch.fetch_states(["a"], base_url="http://evo/", api_key="SEGREDO", transport=httpx.MockTransport(handler))
    assert seen["key"] == "SEGREDO" and out == {"a": "unreachable"}


async def test_alerts_only_after_confirmed_checks_then_not_again():
    state = LineWatchState()
    down = {"loja": "connecting", "b2b": "open"}
    assert await line_watch.evaluate(down, confirm_checks=2, repeat_minutes=60, state=state) == []        # 1ª rodada: sem alarme
    events = await line_watch.evaluate(down, confirm_checks=2, repeat_minutes=60, state=state)           # 2ª: avisa
    assert [(e.kind, e.instance, e.state) for e in events] == [("down", "loja", "connecting")]
    assert await line_watch.evaluate(down, confirm_checks=2, repeat_minutes=60, state=state) == []        # 3ª: dentro da janela, não repete


async def test_blip_does_not_alert_and_recovery_is_announced_once():
    state = LineWatchState()
    await line_watch.evaluate({"loja": "close"}, confirm_checks=2, repeat_minutes=60, state=state)
    assert await line_watch.evaluate({"loja": "open"}, confirm_checks=2, repeat_minutes=60, state=state) == []   # voltou antes de confirmar
    await line_watch.evaluate({"loja": "close"}, confirm_checks=2, repeat_minutes=60, state=state)
    assert [e.kind for e in await line_watch.evaluate({"loja": "close"}, confirm_checks=2, repeat_minutes=60, state=state)] == ["down"]
    assert [e.kind for e in await line_watch.evaluate({"loja": "open"}, confirm_checks=2, repeat_minutes=60, state=state)] == ["recovered"]
    assert await line_watch.evaluate({"loja": "open"}, confirm_checks=2, repeat_minutes=60, state=state) == []


def test_pick_sender_prefers_open_non_personal_line_and_never_the_down_one():
    states = {"loja": "connecting", "pessoal": "open", "b2b": "open"}
    assert line_watch.pick_sender(states, "loja", "pessoal") == "b2b"
    assert line_watch.pick_sender({"loja": "connecting", "pessoal": "open"}, "loja", "pessoal") == "pessoal"
    assert line_watch.pick_sender({"loja": "connecting", "b2b": "close"}, "loja", "pessoal") is None
    assert line_watch.pick_sender({"loja": "open", "b2b": "open"}, "loja", "") == "b2b"


def test_message_texts():
    down = line_watch.message_for(LineEvent("down", "MARQUESCOLOR", "connecting", 2), 120)
    assert "MARQUESCOLOR" in down and "FORA DO AR" in down and "connecting" in down and "4 min" in down and "não responda" in down
    assert "lembrete" in line_watch.message_for(LineEvent("still_down", "x", "close", 30), 120)
    assert "voltou" in line_watch.message_for(LineEvent("recovered", "x", "open"), 120)


def _patch_states(monkeypatch, states):
    async def fake(instances, **kwargs):
        return {i: states.get(i, "unreachable") for i in instances}
    monkeypatch.setattr("jobs.line_watch_job.line_watch.fetch_states", fake)


async def _jobs(session_factory, name):
    async with session_factory() as db:
        return list((await db.execute(select(Job).where(Job.name == name))).scalars().all())


async def test_tick_alerts_via_another_open_line_once_and_reschedules(session_factory, settings, monkeypatch):
    _patch_states(monkeypatch, {"MARQUESCOLOR": "connecting", "b2b-sales": "open", "azusa-church": "open", "Dario": "open"})
    for _ in range(3):
        async with session_factory() as db:
            await line_watch_tick(db, {})
    sends = await _jobs(session_factory, "whatsapp.send_text")
    assert len(sends) == 1                                                       # 2 rodadas confirmam, a 3ª não repete
    payload = sends[0].payload
    assert payload["to"] == "5511999990000" and payload["instance"] == "b2b-sales"   # outra linha, não a pessoal nem a que caiu
    assert "MARQUESCOLOR" in payload["content"]
    assert len(await _jobs(session_factory, JOB_NAME)) == 3                      # a corrente nunca morre
    async with session_factory() as db:
        logs = (await db.execute(select(LogEntry).where(LogEntry.source == "line_watch"))).scalars().all()
    assert len(logs) == 1 and logs[0].level == "error" and logs[0].payload["sent_via"] == "b2b-sales"


async def test_tick_announces_recovery(session_factory, settings, monkeypatch):
    states = {"MARQUESCOLOR": "close", "b2b-sales": "open", "azusa-church": "open", "Dario": "open"}
    _patch_states(monkeypatch, states)
    for _ in range(2):
        async with session_factory() as db:
            await line_watch_tick(db, {})
    states["MARQUESCOLOR"] = "open"
    async with session_factory() as db:
        await line_watch_tick(db, {})
    texts = [j.payload["content"] for j in await _jobs(session_factory, "whatsapp.send_text")]
    assert len(texts) == 2 and "FORA DO AR" in texts[0] and "voltou" in texts[1]


async def test_no_phone_or_no_open_line_only_logs(session_factory, settings, monkeypatch):
    monkeypatch.setattr(settings, "line_watch_alert_phone", "")
    _patch_states(monkeypatch, {"MARQUESCOLOR": "close", "b2b-sales": "open", "azusa-church": "open", "Dario": "open"})
    for _ in range(2):
        async with session_factory() as db:
            await line_watch_tick(db, {})
    assert await _jobs(session_factory, "whatsapp.send_text") == []
    async with session_factory() as db:
        log = (await db.execute(select(LogEntry).where(LogEntry.source == "line_watch"))).scalars().one()
    assert log.payload["no_phone"] is True and log.level == "error"

    line_watch.line_watch_state.reset()
    monkeypatch.setattr(settings, "line_watch_alert_phone", "5511999990000")
    from services.rate_limit import rate_limiter
    rate_limiter._local_windows.clear()
    _patch_states(monkeypatch, {})                                               # tudo unreachable: nenhuma linha no ar
    for _ in range(2):
        async with session_factory() as db:
            await line_watch_tick(db, {})
    assert await _jobs(session_factory, "whatsapp.send_text") == []


async def test_round_error_does_not_kill_the_chain(session_factory, settings, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("evolution caiu feio")
    monkeypatch.setattr("jobs.line_watch_job.line_watch.fetch_states", boom)
    async with session_factory() as db:
        await line_watch_tick(db, {})
    assert len(await _jobs(session_factory, JOB_NAME)) == 1


async def test_start_is_idempotent_and_respects_the_switch(session_factory, settings, monkeypatch):
    monkeypatch.setattr(settings, "line_watch_enabled", False)
    async with session_factory() as db:
        await start(db)
    assert await _jobs(session_factory, JOB_NAME) == []
    monkeypatch.setattr(settings, "line_watch_enabled", True)
    for _ in range(2):
        async with session_factory() as db:
            await start(db)
    assert len(await _jobs(session_factory, JOB_NAME)) == 1


def test_default_watch_list_comes_from_the_configured_instances(settings, monkeypatch):
    monkeypatch.setattr(settings, "line_watch_instances", "")
    monkeypatch.setattr(settings, "evolution_instance", "MARQUESCOLOR")
    assert line_watch.watched_instances(settings) == ["MARQUESCOLOR", "Dario"]


# ---------------------------------------------------------------- alerta do Gêmeo por outra linha quando a da loja cai
def test_alert_instance_switches_only_when_the_default_line_is_known_down(settings, monkeypatch):
    monkeypatch.setattr(settings, "evolution_instance", "MARQUESCOLOR")
    assert line_watch.alert_instance(settings) is None                                   # sem leitura do vigia: comportamento de sempre
    line_watch.record_states({"MARQUESCOLOR": "open", "b2b-sales": "open"})
    assert line_watch.alert_instance(settings) is None                                   # loja no ar: segue pela loja
    line_watch.record_states({"MARQUESCOLOR": "connecting", "b2b-sales": "open", "Dario": "open"})
    assert line_watch.alert_instance(settings) == "b2b-sales"                            # loja fora: outra linha, não a pessoal
    line_watch.record_states({"MARQUESCOLOR": "connecting", "b2b-sales": "close"})
    assert line_watch.alert_instance(settings) is None                                   # nenhuma outra no ar: mantém o padrão
    line_watch.record_states({"MARQUESCOLOR": "connecting", "b2b-sales": "open"})
    line_watch.line_watch_state.last_checked -= 3600
    assert line_watch.alert_instance(settings) is None                                   # leitura velha demais: não confia


async def test_tick_records_the_states_it_read(session_factory, settings, monkeypatch):
    _patch_states(monkeypatch, {"MARQUESCOLOR": "close", "b2b-sales": "open", "azusa-church": "open", "Dario": "open"})
    async with session_factory() as db:
        await line_watch_tick(db, {})
    assert line_watch.line_watch_state.last_states["MARQUESCOLOR"] == "close"
