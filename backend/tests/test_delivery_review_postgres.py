# ruff: noqa: F811
"""Revisão de entregas incertas em PostgreSQL REAL: fechamento administrativo concorrente e fechamento × reserva concorrente.

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


async def test_dois_fechamentos_concorrentes_um_vence_e_a_auditoria_e_unica(pg, api):
    rev = await _revision(pg)
    barrier = asyncio.Barrier(2)

    async def close():
        await asyncio.wait_for(barrier.wait(), 10)
        return await api.post("/api/whatsapp/deliveries/close-unknown", json=_body(pg, rev))
    r1, r2 = await asyncio.gather(close(), close())
    assert sorted([r1.status_code, r2.status_code]) == [200, 409]
    async with pg.sessions() as db:
        n = (await db.execute(text("SELECT count(*) FROM conversation_control_audit WHERE action='close_unknown'"))).scalar()
        ctl = await conversation_control.snapshot(db, pg.contact_id, INSTANCE)
    assert n == 1 and ctl["revision"] == rev + 1 and ctl["paused"] is True


@pytest.mark.parametrize("close_first", [True, False])
async def test_fechamento_e_reserva_com_cerca_concorrentes_nunca_perdem_a_cerca_do_outro(pg, api, close_first):
    """O fechamento (comum) e um claim_send de OUTRO envio disputam a conversa. Em qualquer ordem: se o claim venceu, a cerca dele
    sobrevive ao fechamento; se o fechamento venceu (pausou), o claim é recusado. Nunca fica uma cerca apagada de um envio ativo."""
    rev = await _revision(pg)
    barrier = asyncio.Barrier(2)

    async def close():
        await asyncio.wait_for(barrier.wait(), 10)
        if not close_first:
            await asyncio.sleep(0.05)
        return await api.post("/api/whatsapp/deliveries/close-unknown", json=_body(pg, rev))

    async def claim():
        async with pg.sessions() as db:
            await asyncio.wait_for(barrier.wait(), 10)
            if close_first:
                await asyncio.sleep(0.05)
            result = await conversation_control.claim_send(db, pg.contact_id, INSTANCE, rev, "twin-send:rival-1")
            await db.commit()
            return result
    r_close, claimed = await asyncio.gather(close(), claim())
    async with pg.sessions() as db:
        ctl = await conversation_control.snapshot(db, pg.contact_id, INSTANCE)
    if claimed == "claimed":
        assert ctl["inflight"] == "twin-send:rival-1"                      # o rival ativo mantém a cerca
        assert r_close.status_code in (200, 409)
        if r_close.status_code == 200:
            assert ctl["paused"] is True
    else:
        assert r_close.status_code == 200 and ctl["paused"] is True and ctl["inflight"] is None
