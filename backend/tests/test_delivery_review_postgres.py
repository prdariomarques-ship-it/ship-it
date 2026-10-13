# ruff: noqa: F811
"""Revisão de entregas incertas em PostgreSQL REAL: fechamento administrativo concorrente e fechamento × reserva concorrente.

As corridas são DETERMINÍSTICAS: uma sessão "dona" executa sua operação e segura a trava da conversa sem confirmar; a outra
operação é disparada e só se prossegue quando o `pg_stat_activity` mostra que ela está BLOQUEADA esperando a trava; então a dona
confirma e o resultado da segunda é verificado. Sem `sleep` para decidir a ordem e sem aceitar dois resultados possíveis.

Só roda com TEST_POSTGRES_URL (banco descartável, recriado a cada teste). Sem ela, é pulado."""
import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import jobs.handlers  # noqa: F401
from database.base import Base
from jobs.service import JobService
from jobs.worker import JobWorker
from models.contact import Contact
from auth.password import hash_password
from models.user import User, UserRole
from services import conversation_control
from tests.test_delivery_review_worker import INSTANCE, PHONE, REASON, Provider
from tests.test_whatsapp_send_queue_retry import _migrate_control_tables_sync
from utils.config import get_settings

PG_URL = os.environ.get("TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not PG_URL, reason="defina TEST_POSTGRES_URL (PostgreSQL descartável)")


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
    monkeypatch.setattr(get_settings(), "jobs_retry_backoff_seconds", 0)
    provider = Provider()
    monkeypatch.setattr("jobs.handlers.get_whatsapp_provider", lambda: provider)

    class W:
        pass
    w = W()
    w.sessions, w.provider = sessions, provider
    async with sessions() as db:
        c = Contact(name="C", phone=PHONE, preferences={})
        admin = User(email="admin@example.com", full_name="A", hashed_password=hash_password("testpass123"), role=UserRole.ADMIN, is_active=True)
        db.add_all([c, admin])
        await db.commit()
        w.contact_id, w.admin_id = c.id, admin.id             # o ator da auditoria tem FK para users: precisa existir de verdade
        job = await JobService(db).enqueue("whatsapp.send_text", {"to": PHONE, "content": "Temos sim.", "instance": INSTANCE})
        w.job_id = job.id
    for _ in range(4):
        await JobWorker().run_once()
    assert len(provider.calls) == 1                           # envio comum feito, SEM recibo: needs_review com transporte finalizado
    yield w
    await engine.dispose()


@pytest_asyncio.fixture
async def api(pg):
    from httpx import ASGITransport, AsyncClient

    from auth.dependencies import get_current_user
    from database.session import get_db
    from main import app

    async def override_get_db():
        async with pg.sessions() as session:
            yield session

    class _Admin:
        id, is_active, role = pg.admin_id, True, UserRole.ADMIN
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: _Admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _revision(pg):
    async with pg.sessions() as db:
        return (await conversation_control.snapshot(db, pg.contact_id, INSTANCE))["revision"]


def _body(pg, revision):
    return {"contact_id": pg.contact_id, "instance": INSTANCE, "kind": "send", "key": f"send-job:{pg.job_id}", "expected_revision": revision,
            "reason": REASON, "no_resend_confirmation": True}


async def test_envio_comum_sem_recibo_e_fechado_em_postgres(pg, api):
    r = await api.post("/api/whatsapp/deliveries/close-unknown", json=_body(pg, await _revision(pg)))
    assert r.status_code == 200 and r.json()["intent"]["status"] == "closed_unknown"
    assert len(pg.provider.calls) == 1


async def _wait_blocked(pg, expected=1, timeout=15.0):
    """Espera (consultando o servidor) até haver `expected` sessões presas em trava de linha/transação. Prova que a segunda operação
    chegou ao ponto de espera ANTES de a dona confirmar; falha por tempo se a operação não bloquear (isto é, se não houver trava)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        async with pg.sessions() as db:                     # sessão nova a cada consulta: pg_stat_activity é congelada dentro de uma transação
            n = (await db.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                                       "AND wait_event_type='Lock' AND pid<>pg_backend_pid()"))).scalar()
        if n >= expected:
            return n
        assert loop.time() < deadline, f"nenhuma operação bloqueou na trava da conversa (bloqueadas: {n})"
        await asyncio.sleep(0.01)                           # só intervalo de consulta; não decide a ordem


async def _hold_close(pg, rev):
    """Sessão dona: fecha administrativamente pelo serviço e NÃO confirma (segura a trava da conversa)."""
    db = pg.sessions()
    session = await db.__aenter__()
    await conversation_control.close_unknown(session, pg.contact_id, INSTANCE, "send", f"send-job:{pg.job_id}", rev, pg.admin_id, REASON)
    return db, session


async def _hold_claim(pg, rev, intent):
    db = pg.sessions()
    session = await db.__aenter__()
    assert await conversation_control.claim_send(session, pg.contact_id, INSTANCE, rev, intent) == "claimed"
    return db, session


async def _release(db, session):
    await session.commit()
    await db.__aexit__(None, None, None)


async def _audit_count(pg):
    async with pg.sessions() as db:
        return (await db.execute(text("SELECT count(*) FROM conversation_control_audit WHERE action='close_unknown'"))).scalar()


async def test_fechamento_forcado_dois_fechamentos_o_segundo_espera_e_e_recusado(pg, api):
    rev = await _revision(pg)
    holder = await _hold_close(pg, rev)                       # o primeiro fechamento está feito, mas não confirmado
    second = asyncio.create_task(api.post("/api/whatsapp/deliveries/close-unknown", json=_body(pg, rev)))
    await _wait_blocked(pg)                                    # o segundo está preso na trava (provado no servidor)
    assert not second.done()
    await _release(*holder)
    r = await asyncio.wait_for(second, 15)
    assert r.status_code == 409                                # viu o primeiro já confirmado: já fechado/revisão mudou
    async with pg.sessions() as db:
        ctl = await conversation_control.snapshot(db, pg.contact_id, INSTANCE)
    assert await _audit_count(pg) == 1 and ctl["revision"] == rev + 1 and ctl["paused"] is True
    assert len(pg.provider.calls) == 1                         # nenhum reenvio


async def test_dois_fechamentos_livres_um_vence_e_a_auditoria_e_unica(pg, api):
    """Sem ordem forçada (as duas chamadas largam juntas): qualquer vencedor serve, mas o resultado é sempre exatamente 200 + 409."""
    rev = await _revision(pg)
    barrier = asyncio.Barrier(2)

    async def close():
        await asyncio.wait_for(barrier.wait(), 10)
        return await api.post("/api/whatsapp/deliveries/close-unknown", json=_body(pg, rev))
    r1, r2 = await asyncio.gather(close(), close())
    assert sorted([r1.status_code, r2.status_code]) == [200, 409]
    async with pg.sessions() as db:
        ctl = await conversation_control.snapshot(db, pg.contact_id, INSTANCE)
    assert await _audit_count(pg) == 1 and ctl["revision"] == rev + 1 and ctl["paused"] is True


async def test_reserva_cercada_vence_o_fechamento_espera_preserva_a_cerca_e_a_pausa_permanece_apos_concluir_o_envio(pg, api):
    """Ordem forçada 1: o claim (envio rival) já tem a trava; o fechamento espera, depois fecha SEM apagar a cerca do rival.
    O envio rival é concluído (com recibo) e a pausa colocada pelo fechamento continua."""
    rev = await _revision(pg)
    holder = await _hold_claim(pg, rev, "twin-send:rival-1")
    closing = asyncio.create_task(api.post("/api/whatsapp/deliveries/close-unknown", json=_body(pg, rev)))
    await _wait_blocked(pg)
    assert not closing.done()
    await _release(*holder)
    r = await asyncio.wait_for(closing, 15)
    assert r.status_code == 200 and r.json()["intent"]["status"] == "closed_unknown"
    async with pg.sessions() as db:
        ctl = await conversation_control.snapshot(db, pg.contact_id, INSTANCE)
    assert ctl["paused"] is True and ctl["revision"] == rev + 1
    assert ctl["inflight"] == "twin-send:rival-1"              # a cerca do rival ativo sobreviveu ao fechamento
    async with pg.sessions() as db:                            # o rival termina o envio dele (recibo): só ele libera a própria cerca
        assert await conversation_control.finish_send(db, "twin-send:rival-1", "wamid-rival") == "sent"
        await db.commit()
    async with pg.sessions() as db:
        ctl = await conversation_control.snapshot(db, pg.contact_id, INSTANCE)
        statuses = dict((await db.execute(text("SELECT id, status FROM conversation_send_intents"))).all())
    assert ctl["inflight"] is None and ctl["paused"] is True   # a pausa permanece depois de o envio concorrente concluir
    assert statuses[f"send-job:{pg.job_id}"] == "closed_unknown" and statuses["twin-send:rival-1"] == "sent"
    assert len(pg.provider.calls) == 1                         # o fechamento não enviou nada


async def test_fechamento_vence_a_reserva_cercada_espera_e_e_recusada_sem_cerca(pg, api):
    """Ordem forçada 2: o fechamento já tem a trava (e pausou/subiu a revisão); o claim rival espera e é recusado."""
    rev = await _revision(pg)
    holder = await _hold_close(pg, rev)

    async def claim():
        async with pg.sessions() as db:
            result = await conversation_control.claim_send(db, pg.contact_id, INSTANCE, rev, "twin-send:rival-2")
            await db.commit()
            return result
    claiming = asyncio.create_task(claim())
    await _wait_blocked(pg)
    assert not claiming.done()
    await _release(*holder)
    assert await asyncio.wait_for(claiming, 15) == "suppressed"
    async with pg.sessions() as db:
        ctl = await conversation_control.snapshot(db, pg.contact_id, INSTANCE)
    assert ctl["paused"] is True and ctl["inflight"] is None and ctl["revision"] == rev + 1
    assert await _audit_count(pg) == 1
