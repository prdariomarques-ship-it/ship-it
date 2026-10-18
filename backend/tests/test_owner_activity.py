"""Guarda de atividade do dono (services/owner_activity.py): banco real (SQLite de teste), mensagens reais; nenhum envio."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.contact import Contact
from models.log import LogEntry
from models.message import Message, MessageDirection, MessageMediaType
from services import owner_activity as oa

NOW = datetime(2026, 10, 18, 15, 0, 0, tzinfo=timezone.utc)
B2B = "b2b-sales"


@pytest.fixture
async def sessions(db_engine, tmp_path, monkeypatch):
    monkeypatch.setattr(oa, "WINDOWS_FILE", str(tmp_path / "janelas.txt"))        # arquivo ausente = padrão (180 s)
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _contact(sessions, phone="5511999990001"):
    async with sessions() as db:
        c = Contact(name="Cliente", phone=phone, preferences={})
        db.add(c)
        await db.commit()
        return c.id


async def _msg(sessions, contact_id, *, direction="OUTBOUND", human=True, auto=False, media="TEXT", seconds_ago=30, instance=B2B,
               provider_ts=True, content=""):
    at = NOW - timedelta(seconds=seconds_ago)
    async with sessions() as db:
        m = Message(contact_id=contact_id, direction=MessageDirection[direction], media_type=MessageMediaType[media], content=content,
                    whatsapp_instance=instance, sent_by_human=human, is_autopilot_reply=auto, created_at=at,
                    provider_timestamp=at if provider_ts else None)
        db.add(m)
        await db.commit()
        return m.id


async def _logs(sessions):
    async with sessions() as db:
        return list((await db.execute(select(LogEntry).where(LogEntry.source == "owner_activity_guard"))).scalars().all())


async def test_owner_text_or_media_within_window_suppresses_and_logs_the_event(sessions):
    cid = await _contact(sessions)
    for media in ("TEXT", "AUDIO", "PDF", "IMAGE", "LOCATION"):
        mid = await _msg(sessions, cid, media=media, seconds_ago=60)
        async with sessions() as db:
            assert await oa.pre_check(db, "b2b", cid, 0, B2B, now=NOW) is False, media           # mídia SEM texto conta
        log = (await _logs(sessions))[-1]
        assert log.message == "suppressed_owner_active"
        assert log.payload == {"event": "suppressed_owner_active", "agent": "b2b", "contact_id": cid, "instance": B2B,
                               "owner_message_id": mid, "owner_media": media.lower(), "window_seconds": 180, "phase": "pre"}
        async with sessions() as db:                                                               # limpa para o próximo tipo
            await db.execute(Message.__table__.delete())
            await db.commit()


async def test_inactive_owner_lets_the_agent_through(sessions):
    cid = await _contact(sessions)
    await _msg(sessions, cid, seconds_ago=181)                                                    # fora da janela
    async with sessions() as db:
        assert await oa.pre_check(db, "b2b", cid, 0, B2B, now=NOW) is True
    assert await _logs(sessions) == []


async def test_only_the_owner_counts_not_agents_not_the_twin_not_clients(sessions):
    cid = await _contact(sessions)
    await _msg(sessions, cid, human=False, auto=False, seconds_ago=10)                            # outro agente (B2B/loja)
    await _msg(sessions, cid, human=False, auto=True, seconds_ago=10)                             # gêmeo
    await _msg(sessions, cid, human=True, auto=True, seconds_ago=10)                              # autopilot marcado
    await _msg(sessions, cid, direction="INBOUND", human=False, seconds_ago=10)                   # cliente
    async with sessions() as db:
        assert await oa.pre_check(db, "b2b", cid, 0, B2B, now=NOW) is True


async def test_isolation_by_contact_and_by_line(sessions):
    a, b = await _contact(sessions, "5511999990001"), await _contact(sessions, "5511999990002")
    await _msg(sessions, a, seconds_ago=20)                                                       # dono ativo em A, linha B2B
    await _msg(sessions, b, seconds_ago=20, instance="MARQUESCOLOR")                              # dono ativo em B, outra linha
    async with sessions() as db:
        assert await oa.pre_check(db, "b2b", a, 0, B2B, now=NOW) is False
        assert await oa.pre_check(db, "b2b", b, 0, B2B, now=NOW) is True                          # outro contato, mesma linha: livre
        assert await oa.pre_check(db, "store", a, 0, "MARQUESCOLOR", now=NOW) is True             # mesmo contato, outra linha: livre


async def test_per_agent_window_file_and_disable(sessions, tmp_path):
    cid = await _contact(sessions)
    await _msg(sessions, cid, seconds_ago=120)
    path = tmp_path / "janelas.txt"
    path.write_text("# janelas em segundos\ndefault = 180\nb2b=60\nazusa: 600\nlixo\nstore=abc\n", encoding="utf-8")
    assert oa.load_windows(str(path)) == {"default": 180, "b2b": 60, "azusa": 600}
    async with sessions() as db:
        assert await oa.pre_check(db, "b2b", cid, 0, B2B, now=NOW) is True                        # janela 60 s: 120 s atrás já passou
        assert await oa.pre_check(db, "azusa_intake", cid, 0, B2B, now=NOW) is False             # alias azusa_intake -> 600 s
    path.write_text("b2b=0\n", encoding="utf-8")
    async with sessions() as db:
        assert await oa.pre_check(db, "b2b", cid, 0, B2B, now=NOW) is True                        # 0 desliga


def test_default_window_when_file_is_missing_or_unreadable(tmp_path):
    assert oa.load_windows(str(tmp_path / "nao_existe.txt")) == {}
    assert oa.window_for("b2b", {}) == 180 and oa.window_for("store", {"default": 90}) == 90 and oa.window_for("store", {"store": 0}) == 0


async def test_send_guard_catches_the_owner_who_entered_during_generation(sessions):
    cid = await _contact(sessions)
    payload = {"to": "5511999990001", "content": "oi", "instance": B2B, **oa.guard_payload("b2b", cid, 77)}
    async with sessions() as db:
        assert await oa.send_guard(db, payload, B2B, now=NOW) is True                             # dono inativo no início
    mid = await _msg(sessions, cid, media="AUDIO", seconds_ago=5)                                 # ...e entra DURANTE a geração
    async with sessions() as db:
        assert await oa.send_guard(db, payload, B2B, now=NOW) is False                            # corrida: barrado no envio
    log = (await _logs(sessions))[-1]
    assert log.payload["phase"] == "send" and log.payload["owner_message_id"] == mid and log.payload["agent"] == "b2b"


async def test_unmarked_sends_pass_untouched_even_with_owner_active(sessions):
    cid = await _contact(sessions)
    await _msg(sessions, cid, seconds_ago=5)
    async with sessions() as db:
        assert await oa.send_guard(db, {"to": "x", "content": "alerta"}, B2B, now=NOW) is True   # envio comum / alerta ao dono
    assert await _logs(sessions) == []


async def test_row_without_provider_timestamp_uses_created_at_and_epoch_cannot_disable(sessions):
    cid = await _contact(sessions)
    await _msg(sessions, cid, seconds_ago=30, provider_ts=False)
    async with sessions() as db:
        assert await oa.pre_check(db, "b2b", cid, 0, B2B, now=NOW) is False
    row = type("R", (), {"direction": "outbound", "sent_by_human": True, "is_autopilot_reply": False, "id": 1, "media_type": "text",
                         "provider_timestamp": 1792330000, "created_at": NOW - timedelta(seconds=10)})()
    assert oa.latest_owner_activity([row], 180, NOW) is not None                                  # epoch ignorado, vale created_at


@pytest.mark.parametrize("seconds_ago,suppressed", [(179, True), (180, True), (181, False)])
async def test_window_boundary_is_inclusive_at_180s(sessions, seconds_ago, suppressed):
    cid = await _contact(sessions)
    await _msg(sessions, cid, seconds_ago=seconds_ago)
    async with sessions() as db:
        assert await oa.pre_check(db, "b2b", cid, 0, B2B, now=NOW) is (not suppressed)


async def test_pause_then_resume_follows_the_owner_clock_and_a_new_owner_message_restarts_it(sessions):
    cid = await _contact(sessions)
    await _msg(sessions, cid, seconds_ago=100)                                                    # dono falou aos T-100
    async with sessions() as db:
        assert await oa.pre_check(db, "b2b", cid, 0, B2B, now=NOW) is False                       # pausado
        assert await oa.pre_check(db, "b2b", cid, 0, B2B, now=NOW + timedelta(seconds=79)) is False   # T+79 = 179 s depois
        assert await oa.pre_check(db, "b2b", cid, 0, B2B, now=NOW + timedelta(seconds=81)) is True     # 181 s: retoma
    await _msg(sessions, cid, seconds_ago=-100)                                                   # dono volta a falar aos T+100
    async with sessions() as db:
        assert await oa.pre_check(db, "b2b", cid, 0, B2B, now=NOW + timedelta(seconds=150)) is False   # pausa reiniciada
        assert await oa.pre_check(db, "b2b", cid, 0, B2B, now=NOW + timedelta(seconds=281)) is True    # retoma de novo


async def test_message_suppressed_during_pause_is_not_answered_later(sessions):
    """Documenta o comportamento atual: a guarda só suprime; não reagenda. O cliente que escreveu durante a pausa fica sem resposta do agente."""
    cid = await _contact(sessions)
    await _msg(sessions, cid, seconds_ago=60)
    async with sessions() as db:
        assert await oa.pre_check(db, "b2b", cid, 101, B2B, now=NOW) is False
    assert [l.payload["phase"] for l in await _logs(sessions)] == ["pre"]                          # só registra; nenhum job de retomada existe
