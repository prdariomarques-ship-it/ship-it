"""Catálogo: handler real `catalog.index_product` -> `MemoryManager` real -> `MemoryService` real -> SQL real (SQLite).

Só o Qdrant (cliente) e o provedor de embeddings são substituídos. Prova: SKU ativo indexa; inativo/ausente desindexa; a reindexação
sequencial SUBSTITUI o SKU (um vetor, não acumula) sem tocar em outra origem nem em outro SKU; a chave externa persiste na linha SQL
E no payload do ponto vetorial. NÃO prova idempotência concorrente (duas indexações simultâneas do mesmo SKU)."""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import jobs.handlers as handlers
import memory.service as memory_service_module
from memory.manager import PRODUCT_SOURCE
from memory.service import memory_service
from models.embedding import Embedding
from models.product import Product


@pytest.fixture
async def world(db_engine, monkeypatch):
    client = MagicMock()
    client.upsert, client.delete = AsyncMock(), AsyncMock()
    monkeypatch.setattr(memory_service, "_client", client)
    monkeypatch.setattr(memory_service, "_collection_ready", True)
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 1536)
    monkeypatch.setattr(memory_service_module, "get_embedding_provider", lambda: embedder)

    class W:
        pass
    w = W()
    w.sessions, w.client = async_sessionmaker(db_engine, expire_on_commit=False), client
    return w


async def _product(w, sku, *, active=True, name="Tinta Látex Branca"):
    async with w.sessions() as db:
        db.add(Product(sku=sku, name=name, category="tinta", unit="lata_18L", unit_price=Decimal("199.90"), stock_quantity=3, active=active))
        await db.commit()


async def _run(w, sku):
    async with w.sessions() as db:
        await handlers.index_product(db, {"sku": sku})


async def _rows(w, **where):
    async with w.sessions() as db:
        stmt = select(Embedding)
        for k, v in where.items():
            stmt = stmt.where(getattr(Embedding, k) == v)
        return list((await db.execute(stmt.order_by(Embedding.id))).scalars())


async def test_sku_ativo_indexa_com_a_chave_externa_no_sql_e_no_payload_vetorial(world):
    await _product(world, "TL-18")
    await _run(world, "TL-18")
    (row,) = await _rows(world, source=PRODUCT_SOURCE)
    assert row.external_id == "TL-18" and "Tinta Látex Branca" in row.content and "unidade: lata_18L" in row.content
    (call,) = world.client.upsert.await_args_list
    (point,) = call.kwargs["points"]
    assert point.payload["external_id"] == "TL-18" and point.payload["source"] == PRODUCT_SOURCE and point.id == row.vector_id


async def test_reindexar_o_mesmo_sku_substitui_o_vetor_e_nao_acumula(world):
    await _product(world, "TL-18")
    await _run(world, "TL-18")
    (first,) = await _rows(world, source=PRODUCT_SOURCE)
    async with world.sessions() as db:
        p = (await db.execute(select(Product).where(Product.sku == "TL-18"))).scalar_one()
        p.name = "Tinta Látex Branca Premium"
        await db.commit()
    await _run(world, "TL-18")
    (second,) = await _rows(world, source=PRODUCT_SOURCE)
    assert second.vector_id != first.vector_id and "Premium" in second.content
    world.client.delete.assert_awaited_once()
    assert world.client.delete.await_args.kwargs["points_selector"] == [first.vector_id]      # o vetor antigo foi apagado no Qdrant


async def test_reindexar_nao_toca_em_outro_sku_nem_em_outra_origem_com_a_mesma_chave(world):
    await _product(world, "TL-18")
    await _product(world, "ES-36", name="Esmalte Sintético")
    await _run(world, "ES-36")
    async with world.sessions() as db:                                                   # outra origem usando o MESMO valor de chave
        db.add(Embedding(source="knowledge", content="manual", vector_id="vec-kn", external_id="TL-18"))
        await db.commit()
    await _run(world, "TL-18")
    await _run(world, "TL-18")
    produtos = {r.external_id: r for r in await _rows(world, source=PRODUCT_SOURCE)}
    assert set(produtos) == {"TL-18", "ES-36"}                                           # um vetor por SKU
    assert [r.vector_id for r in await _rows(world, source="knowledge")] == ["vec-kn"]  # a outra origem sobrevive
    assert "vec-kn" not in [c.kwargs["points_selector"][0] for c in world.client.delete.await_args_list]


async def test_sku_inativo_e_sku_ausente_desindexam(world):
    await _product(world, "TL-18")
    await _run(world, "TL-18")
    async with world.sessions() as db:
        (await db.execute(select(Product).where(Product.sku == "TL-18"))).scalar_one().active = False
        await db.commit()
    await _run(world, "TL-18")
    assert await _rows(world, source=PRODUCT_SOURCE) == []
    world.client.delete.assert_awaited_once()
    await _run(world, "NAO-EXISTE")                                                      # ausente: nada a apagar, sem erro
    assert await _rows(world, source=PRODUCT_SOURCE) == []
    assert world.client.upsert.await_count == 1                                          # inativo/ausente nunca gera vetor novo


async def test_desindexar_sem_vetor_previo_nao_chama_o_qdrant(world):
    await _run(world, "SEM-VETOR")
    world.client.delete.assert_not_awaited()
    world.client.upsert.assert_not_awaited()
