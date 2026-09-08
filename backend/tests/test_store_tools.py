"""agents/tools/domain.py -- store domain: product catalog, quoting, order
recording and customer segmentation (Oficina das Tintas / Marquescolor
sales agent)."""

import json
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from agents.tools.base import ToolContext
from agents.tools.domain import (
    add_store_customer_tool,
    create_quote_tool,
    list_products_tool,
    record_order_tool,
    search_products_tool,
    update_store_customer_segment_tool,
)
from models.product import Product
from models.store import StoreCustomer
from models.user import User


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def user(session_factory) -> User:
    async with session_factory() as session:
        user = User(email="prod@example.com", full_name="U", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def paint(session_factory) -> Product:
    async with session_factory() as session:
        product = Product(
            sku="TINTA-LATEX-BR-18L",
            name="Tinta Látex Branca 18L",
            category="tinta_latex",
            unit="lata_18L",
            unit_price=Decimal("289.90"),
            stock_quantity=10,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)
        return product


@pytest.fixture
async def customer(session_factory) -> StoreCustomer:
    async with session_factory() as session:
        customer = StoreCustomer(name="João Pintor", phone="+5511988887777")
        session.add(customer)
        await session.commit()
        await session.refresh(customer)
        return customer


@pytest.mark.asyncio
async def test_add_store_customer_accepts_a_valid_segment(session_factory, user):
    async with session_factory() as session:
        result = await add_store_customer_tool.run(
            ToolContext(db=session, user=user),
            {"name": "Maria Lojista", "segment": "lojista"},
        )
    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["segment"] == "lojista"


@pytest.mark.asyncio
async def test_add_store_customer_rejects_an_invalid_segment(session_factory, user):
    async with session_factory() as session:
        result = await add_store_customer_tool.run(
            ToolContext(db=session, user=user),
            {"name": "Maria", "segment": "atacadista"},
        )
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_update_store_customer_segment(session_factory, user, customer):
    async with session_factory() as session:
        result = await update_store_customer_segment_tool.run(
            ToolContext(db=session, user=user),
            {"customer_name": customer.name, "segment": "pintor"},
        )
    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["segment"] == "pintor"


@pytest.mark.asyncio
async def test_update_store_customer_segment_unknown_customer(session_factory, user):
    async with session_factory() as session:
        result = await update_store_customer_segment_tool.run(
            ToolContext(db=session, user=user),
            {"customer_name": "Ninguém", "segment": "pintor"},
        )
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_list_products_only_returns_active_products(session_factory, user, paint):
    async with session_factory() as session:
        inactive = Product(
            sku="DESCONTINUADO",
            name="Tinta Descontinuada",
            unit="un",
            unit_price=Decimal("10.00"),
            stock_quantity=0,
            active=False,
        )
        session.add(inactive)
        await session.commit()

    async with session_factory() as session:
        result = await list_products_tool.run(
            ToolContext(db=session, user=user), {}
        )
    products = json.loads(result)["products"]
    assert [p["sku"] for p in products] == [paint.sku]


@pytest.mark.asyncio
async def test_search_products_by_name(session_factory, user, paint):
    async with session_factory() as session:
        result = await search_products_tool.run(
            ToolContext(db=session, user=user), {"query": "látex"}
        )
    products = json.loads(result)["products"]
    assert products[0]["sku"] == paint.sku


@pytest.mark.asyncio
async def test_create_quote_computes_totals_from_the_real_catalog(
    session_factory, user, paint
):
    async with session_factory() as session:
        result = await create_quote_tool.run(
            ToolContext(db=session, user=user),
            {"items": [{"sku": paint.sku, "quantity": 3}]},
        )
    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["total"] == "869.70"
    assert payload["items"][0]["line_total"] == "869.70"


@pytest.mark.asyncio
async def test_create_quote_rejects_unknown_sku(session_factory, user, paint):
    async with session_factory() as session:
        result = await create_quote_tool.run(
            ToolContext(db=session, user=user),
            {"items": [{"sku": "NAO-EXISTE", "quantity": 1}]},
        )
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_create_quote_rejects_insufficient_stock(session_factory, user, paint):
    async with session_factory() as session:
        result = await create_quote_tool.run(
            ToolContext(db=session, user=user),
            {"items": [{"sku": paint.sku, "quantity": 999}]},
        )
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_record_order_persists_the_order_and_decrements_stock(
    session_factory, user, paint, customer
):
    async with session_factory() as session:
        result = await record_order_tool.run(
            ToolContext(db=session, user=user),
            {
                "customer_name": customer.name,
                "items": [{"sku": paint.sku, "quantity": 2}],
            },
        )
    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["order"]["total"] == "579.80"
    assert payload["order_count"] == 1

    async with session_factory() as session:
        from repositories.base import SQLAlchemyRepository

        class _ProductRepo(SQLAlchemyRepository[Product]):
            model = Product

        class _StoreRepo(SQLAlchemyRepository[StoreCustomer]):
            model = StoreCustomer

        refreshed_product = await _ProductRepo(session).get(paint.id)
        refreshed_customer = await _StoreRepo(session).get(customer.id)

    assert refreshed_product.stock_quantity == 8
    assert len(refreshed_customer.orders) == 1
    assert refreshed_customer.orders[0]["total"] == "579.80"


@pytest.mark.asyncio
async def test_record_order_rejects_unknown_customer(session_factory, user, paint):
    async with session_factory() as session:
        result = await record_order_tool.run(
            ToolContext(db=session, user=user),
            {
                "customer_name": "Cliente Fantasma",
                "items": [{"sku": paint.sku, "quantity": 1}],
            },
        )
    assert "error" in json.loads(result)
