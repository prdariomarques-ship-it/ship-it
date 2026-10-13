"""Cadeia de migrações reconciliada com o histórico recebido (pacote aftercare-review): o marcador vazio 9e2f1c6d7a80 foi substituído
pela revisão real `store_pos`, precedida das seis revisões históricas. Os arquivos recebidos NÃO provam a versão instalada hoje.

Roda o Alembic de verdade (subprocesso, `DATABASE_URL`) em SQLite SEMPRE e em PostgreSQL quando `TEST_POSTGRES_URL` está definida
(banco descartável: o schema `public` é recriado a cada teste). Cobre: grafo; subida em banco vazio; subida SOBRE a baseline histórica
com dados preexistentes; downgrade que preserva o que a migração não criou; ORM em sessão nova sobre o banco criado pelo Alembic."""
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

BACKEND = Path(__file__).resolve().parents[1]
PG_URL = os.environ.get("TEST_POSTGRES_URL", "")
HISTORY = ["f4c18a2d9e10", "a6217b904c12", "b82f0194de63", "c91d5e7a3b20", "51081d0451d4", "7d31a9b4e2c1", "9e2f1c6d7a80"]
BASELINE = "9e2f1c6d7a80"
HEAD = "c8f3a1d27b40"
WHEN = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.skipif(not PG_URL, reason="defina TEST_POSTGRES_URL"))])
async def url(request, tmp_path):
    if request.param == "sqlite":
        yield f"sqlite+aiosqlite:///{tmp_path / 'chain.db'}"
        return
    engine = create_async_engine(PG_URL, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()
    yield PG_URL


def alembic(url, *args):
    env = dict(os.environ, DATABASE_URL=url)
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, f"alembic {' '.join(args)} falhou:\n{r.stderr[-2500:]}"
    return r


async def schema(url):
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            def read(sync_conn):
                insp = inspect(sync_conn)
                return {t: {c["name"] for c in insp.get_columns(t)} for t in insp.get_table_names()}, \
                       {t: {i["name"] for i in insp.get_indexes(t)} for t in insp.get_table_names()}
            return await conn.run_sync(read)
    finally:
        await engine.dispose()


def test_grafo_tem_uma_cabeca_e_a_ordem_historica_real():
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert script.get_heads() == [HEAD]
    chain = [r.revision for r in script.walk_revisions(base="base", head=HEAD)][::-1]          # do mais antigo ao mais novo
    positions = [chain.index(r) for r in HISTORY]
    assert positions == sorted(positions) and chain[chain.index(BASELINE) + 1:] == ["e610080001", "e610080002", "e610080003", HEAD]
    store_pos = script.get_revision(BASELINE)
    assert store_pos.down_revision == "7d31a9b4e2c1" and "store_pos_orders" in Path(store_pos.path).read_text()   # não é mais o marcador vazio
    assert script.get_revision("f4c18a2d9e10").down_revision == ("6f32d7549a9a", "2cc4e7d820a6")


async def test_subida_em_banco_vazio_cria_as_colunas_e_tabelas_do_historico(url):
    alembic(url, "upgrade", "head")
    tables, indexes = await schema(url)
    assert "awaiting_reply_since" in tables["contacts"] and "external_id" in tables["embeddings"]
    assert {"sent_by_human", "is_autopilot_reply", "whatsapp_instance"} <= tables["messages"]
    assert {"store_quotes", "store_deliveries", "store_support_cases", "store_loop_goals", "store_corrections", "store_pos_orders",
            "store_voice_sends", "store_followups"} <= set(tables)
    assert "ix_embeddings_external_id" in indexes["embeddings"] and "ix_messages_whatsapp_instance" in indexes["messages"]
    engine = create_async_engine(url)
    async with engine.connect() as conn:                       # e610080003 achou tudo já criado pelo histórico: nada seu a remover
        assert (await conn.execute(text("SELECT count(*) FROM _mig_e610080003_created_objects"))).scalar() == 0
    await engine.dispose()


async def _seed_at_baseline(url):
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("INSERT INTO contacts (id, name, phone, categories, preferences, tags, awaiting_reply_since, created_at, updated_at) "
                                "VALUES (1, 'Cli', '5511999996001', '[]', '{}', '[]', :w, :w, :w)"), {"w": WHEN})
        await conn.execute(text("INSERT INTO messages (id, contact_id, direction, media_type, content, sent_by_human, is_autopilot_reply, "
                                "whatsapp_instance, created_at, updated_at) VALUES (1, 1, 'OUTBOUND', 'TEXT', 'oi', :t, :f, 'pessoal', :w, :w)"),
                           {"t": True, "f": False, "w": WHEN})
        await conn.execute(text("INSERT INTO embeddings (id, source, content, vector_id, external_id, created_at, updated_at) "
                                "VALUES (1, 'product_catalog', 'tinta', 'vec-1', 'TL-18', :w, :w)"), {"w": WHEN})
    await engine.dispose()


async def _counts(url):
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        out = (
            (await conn.execute(text("SELECT awaiting_reply_since IS NOT NULL FROM contacts WHERE id=1"))).scalar(),
            (await conn.execute(text("SELECT sent_by_human FROM messages WHERE id=1"))).scalar(),
            (await conn.execute(text("SELECT external_id FROM embeddings WHERE id=1"))).scalar(),
        )
    await engine.dispose()
    return out


async def test_subida_sobre_a_baseline_historica_preserva_dados_e_o_downgrade_nao_remove_o_que_nao_criou(url):
    alembic(url, "upgrade", BASELINE)                          # a baseline: o que a produção já tem
    await _seed_at_baseline(url)
    before_tables, _ = await schema(url)
    alembic(url, "upgrade", "head")
    assert await _counts(url) == (True, True, "TL-18")         # dados e colunas preexistentes intactos
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM _mig_e610080003_created_objects"))).scalar() == 0
    await engine.dispose()
    alembic(url, "downgrade", BASELINE)                        # desfaz só as revisões do branch
    after_tables, _ = await schema(url)
    assert {t: after_tables[t] for t in before_tables} == before_tables       # as colunas do histórico continuam todas lá
    assert "conversation_controls" not in after_tables and "store_followups" not in after_tables      # as revisões do branch saíram
    assert "_mig_e610080003_created_objects" not in after_tables                    # nada reivindicado ⇒ a tabela de propriedade sai vazia
    assert await _counts(url) == (True, True, "TL-18")
    alembic(url, "downgrade", "base")                          # e o ciclo completo continua fechando
    alembic(url, "upgrade", "head")


async def test_orm_em_sessao_nova_sobre_banco_criado_pelo_alembic(url):
    alembic(url, "upgrade", "head")
    from models.contact import Contact
    from models.embedding import Embedding
    from models.message import Message, MessageDirection, MessageMediaType

    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as db:
        c = Contact(name="Cli", phone="5511999996002", preferences={}, awaiting_reply_since=WHEN)
        db.add(c)
        await db.flush()
        db.add(Message(contact_id=c.id, direction=MessageDirection.OUTBOUND, media_type=MessageMediaType.TEXT, content="oi", sent_by_human=True,
                       whatsapp_instance="pessoal"))
        db.add(Embedding(source="product_catalog", content="tinta", vector_id="vec-orm", external_id="TL-18"))
        await db.commit()
        cid = c.id
    async with sessions() as db:                               # sessão NOVA: lê do banco, não do cache
        got = (await db.execute(select(Contact).where(Contact.id == cid))).scalar_one()
        assert got.awaiting_reply_since is not None
        got.awaiting_reply_since = None
        await db.commit()
    async with sessions() as db:
        assert (await db.get(Contact, cid)).awaiting_reply_since is None
        emb = (await db.execute(select(Embedding).where(Embedding.vector_id == "vec-orm"))).scalar_one()
        assert emb.external_id == "TL-18"
    await engine.dispose()
