"""Regression coverage for the catalog and Twin contract gaps in PR #63."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import jobs.handlers as handlers
import memory.service as memory_service_module
from memory.manager import PRODUCT_SOURCE
from memory.service import memory_service
from models.contact import Contact
from models.embedding import Embedding
from models.job import Job
from models.product import Product
from providers.whatsapp.base import InboundMessage
from utils.config import get_settings
from webhooks import router as webhook_router

WHEN = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def sessions(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def qdrant(monkeypatch):
    client = MagicMock()
    client.upsert = AsyncMock()
    client.delete = AsyncMock()
    monkeypatch.setattr(memory_service, "_client", client)
    monkeypatch.setattr(memory_service, "_collection_ready", True)

    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 1536)
    monkeypatch.setattr(memory_service_module, "get_embedding_provider", lambda: embedder)
    return client


async def _add_product(
    sessions, sku: str, *, active: bool = True, name: str = "Tinta Látex Branca"
) -> None:
    async with sessions() as db:
        db.add(
            Product(
                sku=sku,
                name=name,
                category="tinta",
                unit="lata_18L",
                unit_price=Decimal("199.90"),
                stock_quantity=3,
                active=active,
            )
        )
        await db.commit()


async def _run_catalog_job(sessions, sku: str) -> None:
    async with sessions() as db:
        await handlers.index_product(db, {"sku": sku})


async def _embeddings(sessions, *, source: str | None = None) -> list[Embedding]:
    async with sessions() as db:
        statement = select(Embedding).order_by(Embedding.id)
        if source is not None:
            statement = statement.where(Embedding.source == source)
        return list((await db.execute(statement)).scalars().all())


@pytest.mark.asyncio
async def test_catalog_job_indexes_and_replaces_a_product_by_sku(sessions, qdrant):
    await _add_product(sessions, "TL-18")
    await _run_catalog_job(sessions, "TL-18")

    (first,) = await _embeddings(sessions, source=PRODUCT_SOURCE)
    assert first.external_id == "TL-18"
    assert "Tinta Látex Branca" in first.content
    first_point = qdrant.upsert.await_args_list[0].kwargs["points"][0]
    assert first_point.payload["external_id"] == "TL-18"
    assert first_point.payload["source"] == PRODUCT_SOURCE
    assert first_point.id == first.vector_id

    async with sessions() as db:
        product = (
            await db.execute(select(Product).where(Product.sku == "TL-18"))
        ).scalar_one()
        product.name = "Tinta Látex Branca Premium"
        await db.commit()
    await _run_catalog_job(sessions, "TL-18")

    (replacement,) = await _embeddings(sessions, source=PRODUCT_SOURCE)
    assert replacement.external_id == "TL-18"
    assert replacement.vector_id == first.vector_id
    assert "Premium" in replacement.content
    qdrant.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_reindex_failure_preserves_existing_vector_and_metadata(
    sessions, qdrant, monkeypatch
):
    await _add_product(sessions, "TL-18")
    await _run_catalog_job(sessions, "TL-18")
    (original,) = await _embeddings(sessions, source=PRODUCT_SOURCE)
    embedder = MagicMock()
    embedder.embed = AsyncMock(side_effect=RuntimeError("embedding unavailable"))
    monkeypatch.setattr(memory_service_module, "get_embedding_provider", lambda: embedder)

    with pytest.raises(RuntimeError, match="embedding unavailable"):
        await _run_catalog_job(sessions, "TL-18")

    (remaining,) = await _embeddings(sessions, source=PRODUCT_SOURCE)
    assert remaining.vector_id == original.vector_id
    assert remaining.content == original.content
    qdrant.delete.assert_not_awaited()
    assert qdrant.upsert.await_count == 1


@pytest.mark.asyncio
async def test_upsert_failure_does_not_delete_old_vector_or_metadata(sessions, qdrant):
    await _add_product(sessions, "TL-18")
    await _run_catalog_job(sessions, "TL-18")
    (original,) = await _embeddings(sessions, source=PRODUCT_SOURCE)
    qdrant.upsert.side_effect = RuntimeError("Qdrant unavailable")
    with pytest.raises(RuntimeError, match="Qdrant unavailable"):
        await _run_catalog_job(sessions, "TL-18")
    (remaining,) = await _embeddings(sessions, source=PRODUCT_SOURCE)
    assert remaining.vector_id == original.vector_id
    assert remaining.content == original.content
    qdrant.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_preexisting_duplicate_metadata_is_not_silently_destroyed(sessions, qdrant):
    await _add_product(sessions, "TL-18")
    async with sessions() as db:
        for suffix in ("a", "b"):
            db.add(Embedding(
                source=PRODUCT_SOURCE,
                external_id="TL-18",
                content=f"Legacy {suffix}",
                vector_id=f"legacy-{suffix}",
            ))
        await db.commit()
    with pytest.raises(RuntimeError, match="explicit reconciliation"):
        await _run_catalog_job(sessions, "TL-18")
    assert len(await _embeddings(sessions, source=PRODUCT_SOURCE)) == 2
    qdrant.delete.assert_not_awaited()
    qdrant.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_same_sku_jobs_converge_to_one_record(sessions, qdrant):
    """SQLite/local-lock regression, not a PostgreSQL advisory-lock proof."""
    await _add_product(sessions, "TL-18")
    await asyncio.gather(*(_run_catalog_job(sessions, "TL-18") for _ in range(3)))
    (row,) = await _embeddings(sessions, source=PRODUCT_SOURCE)
    assert row.external_id == "TL-18"
    point_ids = {
        call.kwargs["points"][0].id for call in qdrant.upsert.await_args_list
    }
    assert point_ids == {row.vector_id}
    qdrant.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_catalog_deindex_is_scoped_and_missing_sku_is_a_noop(sessions, qdrant):
    await _add_product(sessions, "TL-18")
    await _add_product(sessions, "ES-36", name="Esmalte Sintético")
    await _run_catalog_job(sessions, "TL-18")
    await _run_catalog_job(sessions, "ES-36")
    (first_product,) = [
        row for row in await _embeddings(sessions, source=PRODUCT_SOURCE)
        if row.external_id == "TL-18"
    ]

    async with sessions() as db:
        db.add(
            Embedding(
                source="knowledge",
                content="Manual com a mesma chave externa",
                vector_id="knowledge-vector",
                external_id="TL-18",
            )
        )
        product = (
            await db.execute(select(Product).where(Product.sku == "TL-18"))
        ).scalar_one()
        product.active = False
        await db.commit()

    await _run_catalog_job(sessions, "TL-18")
    await _run_catalog_job(sessions, "SKU-AUSENTE")

    remaining_products = await _embeddings(sessions, source=PRODUCT_SOURCE)
    assert [(row.external_id) for row in remaining_products] == ["ES-36"]
    knowledge_rows = await _embeddings(sessions, source="knowledge")
    assert [(row.external_id, row.vector_id) for row in knowledge_rows] == [
        ("TL-18", "knowledge-vector")
    ]
    assert qdrant.upsert.await_count == 2
    assert qdrant.delete.await_count == 1
    assert qdrant.delete.await_args.kwargs["points_selector"] == [first_product.vector_id]


async def _reload_pending_marker(sessions, contact_id: int) -> datetime | None:
    async with sessions() as db:
        result = await db.execute(select(Contact).where(Contact.id == contact_id))
        value = result.scalar_one().awaiting_reply_since
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@pytest.mark.asyncio
async def test_contact_pending_marker_persists_across_sessions(sessions):
    async with sessions() as db:
        contact = Contact(
            name="Contato de teste",
            phone="5511999995101",
            awaiting_reply_since=WHEN,
        )
        db.add(contact)
        await db.commit()
        contact_id = contact.id

    assert await _reload_pending_marker(sessions, contact_id) == WHEN

    async with sessions() as db:
        contact = await db.get(Contact, contact_id)
        assert contact is not None
        contact.awaiting_reply_since = None
        await db.commit()
    assert await _reload_pending_marker(sessions, contact_id) is None


async def _dispatch_inbound(
    sessions,
    monkeypatch,
    *,
    twin: bool,
    instance: str = "darioos",
    personal: str = "",
    phone: str = "5511999995102",
):
    settings = get_settings()
    monkeypatch.setattr(settings, "auto_reply_enabled", True)
    monkeypatch.setattr(settings, "store_whatsapp_enabled", True)
    monkeypatch.setattr(settings, "whatsapp_twin_mode_enabled", twin)
    monkeypatch.setattr(settings, "evolution_personal_instance", personal)

    async def no_memory_work(*args, **kwargs):
        return False

    async def allowed(*args, **kwargs):
        return True

    monkeypatch.setattr(
        webhook_router.contact_memory_service, "record_interaction", no_memory_work
    )
    monkeypatch.setattr(webhook_router.rate_limiter, "is_allowed", allowed)

    async with sessions() as db:
        contact = Contact(name="Contato de teste", phone=phone)
        db.add(contact)
        await db.commit()
        await db.refresh(contact)
        inbound = InboundMessage(
            phone=phone,
            text="Oi, tem tinta?",
            external_id="EVENT-1",
            instance=instance,
            timestamp=WHEN,
        )
        await webhook_router.dispatch_inbound(
            db,
            SimpleNamespace(name="evolution"),
            inbound,
            contact,
            SimpleNamespace(id=1),
            "text",
        )
        contact_id = contact.id
        await db.commit()

    async with sessions() as db:
        jobs = list((await db.execute(select(Job))).scalars())
    return contact_id, [job.name for job in jobs]


@pytest.mark.asyncio
async def test_twin_enabled_persists_pending_marker_and_enqueues_check(sessions, monkeypatch):
    contact_id, jobs = await _dispatch_inbound(sessions, monkeypatch, twin=True)
    assert await _reload_pending_marker(sessions, contact_id) == WHEN
    assert "whatsapp.twin_autopilot_check" in jobs


@pytest.mark.asyncio
async def test_twin_disabled_or_store_instance_does_not_set_pending_marker(
    sessions, monkeypatch
):
    contact_id, jobs = await _dispatch_inbound(
        sessions, monkeypatch, twin=False, phone="5511999995102"
    )
    assert await _reload_pending_marker(sessions, contact_id) is None
    assert "whatsapp.twin_autopilot_check" not in jobs

    contact_id, jobs = await _dispatch_inbound(
        sessions,
        monkeypatch,
        twin=True,
        instance="loja",
        personal="pessoal",
        phone="5511999995103",
    )
    assert await _reload_pending_marker(sessions, contact_id) is None
    assert "whatsapp.twin_autopilot_check" not in jobs


def _load_contract_migration():
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "e610080004_contract_fields.py"
    )
    spec = spec_from_file_location("e610080004_contract_fields", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _legacy_schema(*, awaiting: bool = False, external: bool = False, index: bool = False):
    engine = sa.create_engine("sqlite:///:memory:")
    contact_extra = ", awaiting_reply_since DATETIME" if awaiting else ""
    embedding_extra = ", external_id VARCHAR(255)" if external else ""
    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"CREATE TABLE contacts (id INTEGER PRIMARY KEY{contact_extra})"
        )
        connection.exec_driver_sql(
            "CREATE TABLE embeddings (id INTEGER PRIMARY KEY, "
            "source VARCHAR(100) NOT NULL, content TEXT NOT NULL, "
            f"vector_id VARCHAR(64) NOT NULL{embedding_extra})"
        )
        if index:
            connection.exec_driver_sql(
                "CREATE INDEX ix_embeddings_external_id ON embeddings (external_id)"
            )
    return engine


def _run_migration(engine, function):
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            function()


def test_contract_migration_adds_and_reverses_only_its_empty_objects():
    engine = _legacy_schema()
    migration = _load_contract_migration()
    _run_migration(engine, migration.upgrade)
    inspector = sa.inspect(engine)
    assert "awaiting_reply_since" in {
        column["name"] for column in inspector.get_columns("contacts")
    }
    assert "external_id" in {
        column["name"] for column in inspector.get_columns("embeddings")
    }
    assert "ix_embeddings_external_id" in {
        index["name"] for index in inspector.get_indexes("embeddings")
    }

    _run_migration(engine, migration.downgrade)
    inspector = sa.inspect(engine)
    assert "awaiting_reply_since" not in {
        column["name"] for column in inspector.get_columns("contacts")
    }
    assert "external_id" not in {
        column["name"] for column in inspector.get_columns("embeddings")
    }
    assert not inspector.has_table("_mig_e610080004_created_objects")
    engine.dispose()


def test_contract_migration_preserves_preexisting_schema_and_foreign_index():
    engine = _legacy_schema(awaiting=True, external=True, index=True)
    migration = _load_contract_migration()
    _run_migration(engine, migration.upgrade)
    _run_migration(engine, migration.downgrade)

    inspector = sa.inspect(engine)
    assert "awaiting_reply_since" in {
        column["name"] for column in inspector.get_columns("contacts")
    }
    assert "external_id" in {
        column["name"] for column in inspector.get_columns("embeddings")
    }
    assert "ix_embeddings_external_id" in {
        index["name"] for index in inspector.get_indexes("embeddings")
    }
    engine.dispose()


def test_contract_migration_downgrade_refuses_to_drop_pending_state():
    engine = _legacy_schema()
    migration = _load_contract_migration()
    _run_migration(engine, migration.upgrade)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO contacts (id, awaiting_reply_since) "
            "VALUES (1, '2026-10-13 12:00:00')"
        )

    with pytest.raises(RuntimeError, match="remove data"):
        _run_migration(engine, migration.downgrade)
    assert sa.inspect(engine).has_table("_mig_e610080004_created_objects")
    engine.dispose()


def test_contract_migration_upgrade_can_be_repeated_without_losing_ownership():
    engine = _legacy_schema()
    migration = _load_contract_migration()
    _run_migration(engine, migration.upgrade)
    _run_migration(engine, migration.upgrade)
    _run_migration(engine, migration.downgrade)
    assert "external_id" not in {
        column["name"] for column in sa.inspect(engine).get_columns("embeddings")
    }
    engine.dispose()


def test_contract_migration_refuses_to_drop_external_keys():
    engine = _legacy_schema()
    migration = _load_contract_migration()
    _run_migration(engine, migration.upgrade)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO embeddings (id, source, content, vector_id, external_id) "
            "VALUES (1, 'product_catalog', 'Tinta', 'vector', 'TL-18')"
        )
    with pytest.raises(RuntimeError, match="remove data"):
        _run_migration(engine, migration.downgrade)
    engine.dispose()


def test_contract_migration_refuses_downgrade_without_ownership_record():
    engine = _legacy_schema(awaiting=True, external=True, index=True)
    migration = _load_contract_migration()
    with pytest.raises(RuntimeError, match="ownership record"):
        _run_migration(engine, migration.downgrade)
    engine.dispose()
