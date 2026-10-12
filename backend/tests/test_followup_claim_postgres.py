# ruff: noqa: F811
"""Claim concorrente de acompanhamentos em PostgreSQL REAL (duas sessões, barreira depois da seleção).

SQLite sequencial não demonstra esta concorrência. O teste só roda com um PostgreSQL descartável indicado em
TEST_POSTGRES_URL (ex.: postgresql+asyncpg://usuario@127.0.0.1:55432/banco_de_teste); sem ela, é pulado. O banco é recriado
(drop_all/create_all) a cada teste: NUNCA aponte para um banco com dados.
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import jobs.handlers  # noqa: F401
from database.base import Base
from jobs.worker import JobWorker
from models.contact import Contact
from models.job import Job
from models.message import Message, MessageDirection, MessageMediaType
from models.product import Product
from models.store import StoreCustomer, StoreQuote
from models.store_followup import StoreFollowup
from services import conversation_control, store_followups as sf, store_optout
from tests.test_store_voice import TextTransport
from tests.test_whatsapp_send_queue_retry import _migrate_control_tables_sync
from utils.config import get_settings

PG_URL = os.environ.get("TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not PG_URL, reason="defina TEST_POSTGRES_URL (PostgreSQL descartável) para provar a concorrência real")

NOW = datetime(2026, 10, 6, 13, 0, tzinfo=timezone.utc)
PHONE, STORE = "5511999990000", "MARQUESCOLOR"


@pytest_asyncio.fixture
async def pg(monkeypatch):
    engine = create_async_engine(PG_URL, pool_size=10)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("DROP SCHEMA public CASCADE")
        await conn.exec_driver_sql("CREATE SCHEMA public")
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_control_tables_sync)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("jobs.worker.async_session_factory", sessions)
    s = get_settings()
    for k, v in dict(
        store_followups_enabled=True, store_whatsapp_enabled=True, auto_reply_enabled=True, evolution_instance=STORE,
        evolution_personal_instance="pessoal-teste", jobs_retry_backoff_seconds=0, store_voice_enabled=False,
        store_timezone="America/Sao_Paulo", store_followup_close_margin_minutes=30, store_hours_confirmed=True,
        store_hours='{"mon-fri": ["08:30", "17:30"], "sat": ["08:30", "12:30"], "holiday": ["08:30", "12:30"]}',
        store_extra_holidays="", store_excluded_holidays="", store_followup_quote_resume_delay_minutes=120, store_followup_max_age_days=7,
        store_followup_max_attempts=1, store_followup_min_gap_hours=72,
    ).items():
        monkeypatch.setattr(s, k, v)
    text_t = TextTransport()
    monkeypatch.setattr("jobs.handlers.get_whatsapp_provider", lambda: text_t)
    monkeypatch.setattr(sf, "_now", lambda: NOW)

    class Env:
        pass
    e = Env()
    e.sessions, e.text, e.engine = sessions, text_t, engine
    async with sessions() as db:
        db.add(Product(sku="TL18", name="Tinta Látex Branca 18L", unit="lata_18L", unit_price=450, stock_quantity=10, active=True))
        contact = Contact(name="Marina Souza", phone=PHONE, preferences={})
        customer = StoreCustomer(name="Marina Souza", phone=PHONE, orders=[])
        db.add_all([contact, customer])
        await db.flush()
        db.add(Message(contact_id=contact.id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT, content="Oi",
                       whatsapp_instance=STORE, created_at=NOW - timedelta(days=3)))
        created = NOW - timedelta(hours=5)
        db.add(StoreQuote(id="ABC123DEF456", contact_id=contact.id, customer_id=customer.id, total=900,
                          items=[dict(sku="TL18", name="Tinta Látex Branca 18L", unit="lata_18L", quantity=2, unit_price="450.00", line_total="900.00")],
                          expires_at=created + timedelta(minutes=30), confirmed_at=None, created_at=created))
        await db.commit()
        e.contact_id = contact.id
        await sf.plan_quote_resumes(db, now=NOW, apply=True)
    yield e
    await engine.dispose()


async def test_duas_sessoes_com_barreira_apos_a_selecao_geram_um_unico_job(pg, monkeypatch):
    barrier = asyncio.Barrier(2)
    original = sf._revalidate

    async def after_select_wait(db, fu, now, s):
        out = await original(db, fu, now, s)
        await asyncio.wait_for(barrier.wait(), 10)              # as DUAS sessões já selecionaram a linha 'scheduled'
        return out
    monkeypatch.setattr(sf, "_revalidate", after_select_wait)

    async def one():
        async with pg.sessions() as db:
            return await sf.run_due(db, now=NOW, apply=True)
    r1, r2 = await asyncio.gather(one(), one())
    actions = sorted(e["action"] for e in r1 + r2)
    assert actions == ["queued", "skip"], actions               # uma ganhou o claim; a outra viu o estado mudar e não criou job
    async with pg.sessions() as db:
        jobs = (await db.scalars(select(Job).where(Job.name == "whatsapp.send_text"))).all()
        assert len(jobs) == 1
        (fu,) = (await db.scalars(select(StoreFollowup))).all()
        assert (fu.status, fu.attempts, fu.job_id) == ("queued", 1, jobs[0].id)
    monkeypatch.setattr(sf, "_revalidate", original)             # a barreira vale só para a seleção; o guard do envio usa o real
    for _ in range(4):
        await JobWorker().run_once()
    assert len(pg.text.calls) == 1                               # uma única chamada ao provedor


async def test_tres_processadores_simultaneos(pg, monkeypatch):
    barrier = asyncio.Barrier(3)
    original = sf._revalidate

    async def after_select_wait(db, fu, now, s):
        out = await original(db, fu, now, s)
        await asyncio.wait_for(barrier.wait(), 10)
        return out
    monkeypatch.setattr(sf, "_revalidate", after_select_wait)

    async def one():
        async with pg.sessions() as db:
            return await sf.run_due(db, now=NOW, apply=True)
    results = await asyncio.gather(one(), one(), one())
    assert sorted(e["action"] for r in results for e in r) == ["queued", "skip", "skip"]
    async with pg.sessions() as db:
        assert len((await db.scalars(select(Job).where(Job.name == "whatsapp.send_text"))).all()) == 1


async def test_opt_out_e_reserva_ficam_ordenados_pela_trava_da_conversa(pg):
    """O guard roda sob a trava da conversa; o opt-out também a toma. Se o opt-out vier primeiro, o envio é bloqueado."""
    async with pg.sessions() as db:
        (entry,) = await sf.run_due(db, now=NOW, apply=True)
        assert entry["action"] == "queued"
    async with pg.sessions() as db:                              # opt-out confirmado ANTES de o worker reservar
        contact = await db.get(Contact, pg.contact_id)
        msg = Message(contact_id=pg.contact_id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT, content="PARAR",
                      whatsapp_instance=STORE, created_at=NOW - timedelta(minutes=1))
        db.add(msg)
        await db.flush()
        assert await store_optout.handle_inbound(db, contact, msg) == store_optout.ACK_OPTOUT
    for _ in range(4):
        await JobWorker().run_once()
    assert pg.text.calls == []
    async with pg.sessions() as db:
        n = (await db.execute(text("SELECT count(*) FROM conversation_send_intents"))).scalar()
        assert n == 0


async def test_reserva_em_andamento_segura_o_opt_out_ate_o_commit(pg):
    """Uma reserva/conferência em andamento (trava da conversa tomada, sem commit) faz o opt-out ESPERAR: os dois ficam em ordem
    total, sem janela entre a conferência do envio e a gravação da recusa."""
    sess_a = pg.sessions()
    db_a = await sess_a.__aenter__()
    sess_b = pg.sessions()
    db_b = await sess_b.__aenter__()
    try:
        await conversation_control.lock_scope(db_a, pg.contact_id, STORE)   # o envio está dentro de reserve_plain_send
        contact = await db_b.get(Contact, pg.contact_id)
        msg = Message(contact_id=pg.contact_id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT, content="PARAR",
                      whatsapp_instance=STORE, created_at=NOW - timedelta(minutes=1))
        db_b.add(msg)
        await db_b.flush()
        optout = asyncio.create_task(store_optout.handle_inbound(db_b, contact, msg))
        await asyncio.sleep(1.0)
        assert not optout.done()                                             # o opt-out espera a trava
        await db_a.commit()                                                  # a reserva termina
        assert await asyncio.wait_for(optout, 15) == store_optout.ACK_OPTOUT
    finally:
        await sess_b.__aexit__(None, None, None)
        await sess_a.__aexit__(None, None, None)
    async with pg.sessions() as db:
        assert (await db.get(Contact, pg.contact_id)).preferences["store_contact_opt_out"] is True


async def test_guard_roda_sob_a_trava_e_enxerga_a_recusa_gravada_antes(pg):
    """Ordem inversa: com o opt-out já confirmado, a reserva (via worker real) é bloqueada pelo guard."""
    async with pg.sessions() as db:
        await sf.run_due(db, now=NOW, apply=True)
    async with pg.sessions() as db:
        contact = await db.get(Contact, pg.contact_id)
        contact.preferences = {"store_contact_opt_out": True, "store_followup_opt_out": True}
        await db.commit()
    for _ in range(4):
        await JobWorker().run_once()
    assert pg.text.calls == []
    async with pg.sessions() as db:
        assert (await db.scalars(select(StoreFollowup))).one().status == "cancelled"


async def test_dois_acompanhamentos_do_mesmo_contato_em_paralelo_geram_no_maximo_um_envio(pg, monkeypatch):
    """Ocorrências DIFERENTES do mesmo contato, processadas por duas sessões ao mesmo tempo: o intervalo mínimo entre contatos
    proativos continua valendo no envio (guard sob a trava da conversa): no máximo UMA chamada ao provedor."""
    async with pg.sessions() as db:
        created = NOW - timedelta(hours=6)
        customer_id = (await db.scalars(select(StoreCustomer.id))).one()
        db.add(StoreQuote(id="ZZZ999YYY888", contact_id=pg.contact_id, customer_id=customer_id, total=900,
                          items=[dict(sku="TL18", name="Tinta Látex Branca 18L", unit="lata_18L", quantity=1, unit_price="450.00", line_total="450.00")],
                          expires_at=created + timedelta(minutes=30), confirmed_at=None, created_at=created))
        await db.commit()
        await sf.plan_quote_resumes(db, now=NOW, apply=True)
        assert len((await db.scalars(select(StoreFollowup))).all()) == 2
    async with pg.sessions() as db:
        ids = [f.id for f in (await db.scalars(select(StoreFollowup).order_by(StoreFollowup.id))).all()]
    barrier = asyncio.Barrier(2)
    original = sf._revalidate

    async def after_select_wait(db, fu, now, s):
        out = await original(db, fu, now, s)              # as duas revalidações terminam ANTES de qualquer uma enfileirar
        await asyncio.wait_for(barrier.wait(), 10)
        return out
    monkeypatch.setattr(sf, "_revalidate", after_select_wait)

    async def one(fid):
        async with pg.sessions() as db:
            return await sf.run_due(db, now=NOW, apply=True, followup_ids=[fid])
    results = await asyncio.gather(one(ids[0]), one(ids[1]))
    assert sorted(e["action"] for r in results for e in r) == ["queued", "queued"]      # a corrida de fato aconteceu: dois jobs
    monkeypatch.setattr(sf, "_revalidate", original)
    for _ in range(6):
        await JobWorker().run_once()
    assert len(pg.text.calls) == 1                         # o guard sob a trava deixa passar só um
    async with pg.sessions() as db:
        statuses = sorted(f.status for f in (await db.scalars(select(StoreFollowup))).all())
    assert statuses == ["cancelled", "queued"], statuses


@pytest.mark.parametrize("texto", ["quero áudio", "só texto", "não tenho interesse"])
async def test_duas_sessoes_com_barreira_apos_as_leituras_iniciais_preservam_o_opt_out(pg, texto):
    """Revisão do commit a526602: duas sessões leem o contato (preferences={}), esperam uma pela outra e SÓ ENTÃO escrevem —
    PARAR e outro escritor concorrentes. Qualquer ordem de execução termina com as flags permanentes verdadeiras."""
    barrier = asyncio.Barrier(2)

    async def writer(content):
        async with pg.sessions() as db:
            contact = await db.get(Contact, pg.contact_id)
            assert contact.preferences == {}                                # leitura inicial, antes de qualquer escrita
            msg = Message(contact_id=pg.contact_id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT, content=content,
                          whatsapp_instance=STORE, created_at=NOW - timedelta(minutes=1))
            db.add(msg)
            await db.flush()
            await asyncio.wait_for(barrier.wait(), 10)                      # as DUAS leituras já aconteceram
            return await store_optout.handle_inbound(db, contact, msg)
    # ordem forçada nas duas direções: o segundo a obter a trava é quem tem o objeto defasado
    r = await asyncio.gather(writer("PARAR"), writer(texto))
    assert store_optout.ACK_OPTOUT in r
    async with pg.sessions() as db:
        prefs = (await db.get(Contact, pg.contact_id)).preferences
    assert prefs["store_contact_opt_out"] is True and prefs["store_followup_opt_out"] is True and "store_contact_opt_out_at" in prefs
    # o acompanhamento posterior não chama o provedor
    async with pg.sessions() as db:
        await sf.run_due(db, now=NOW, apply=True)
    for _ in range(4):
        await JobWorker().run_once()
    assert pg.text.calls == []
