# ruff: noqa: F811
"""A03 (parte verificável por código) — os dados comerciais que o agente recebe vêm das FERRAMENTAS, com sinal explícito de lacuna:
produto inexistente, estoque zerado, preço alterado e falha do catálogo. O comportamento do MODELO diante desses sinais (chamar
`report_unknown`, não adivinhar) NÃO é testado aqui: depende de LLM real."""
import json
from decimal import Decimal

from agents.tools.base import ToolContext
from agents.tools.domain import create_quote_tool, search_products_tool
from models.product import Product
from tests.test_store_tools import paint, session_factory, user  # noqa: F401


async def _run(session_factory, user, tool, args):
    async with session_factory() as session:
        return json.loads(await tool.run(ToolContext(db=session, user=user), args))


async def test_produto_inexistente_volta_lista_vazia_e_nao_inventa_item(session_factory, user, paint):
    out = await _run(session_factory, user, search_products_tool, {"query": "antichamas hospitalar"})
    assert out["products"] == []


async def test_orcamento_de_produto_inexistente_e_erro_explicito_sem_total(session_factory, user, paint):
    out = await _run(session_factory, user, create_quote_tool, {"items": [{"sku": "NAO-EXISTE", "quantity": 1}]})
    assert "error" in out and "total" not in out and "items" not in out


async def test_estoque_zerado_nao_vira_orcamento(session_factory, user, paint):
    async with session_factory() as s:
        p = await s.get(Product, paint.id)
        p.stock_quantity = 0
        await s.commit()
    out = await _run(session_factory, user, create_quote_tool, {"items": [{"sku": paint.sku, "quantity": 1}]})
    assert "error" in out and "total" not in out


async def test_preco_alterado_no_catalogo_aparece_no_proximo_orcamento(session_factory, user, paint):
    before = await _run(session_factory, user, create_quote_tool, {"items": [{"sku": paint.sku, "quantity": 2}]})
    assert before["total"] == "579.80"
    async with session_factory() as s:
        p = await s.get(Product, paint.id)
        p.unit_price = Decimal("310.00")
        await s.commit()
    after = await _run(session_factory, user, create_quote_tool, {"items": [{"sku": paint.sku, "quantity": 2}]})
    assert after["total"] == "620.00" and after["items"][0]["unit_price"] == "310.00"      # nada em cache: o preço vem do registro


async def test_falha_do_catalogo_chega_ao_agente_como_erro_e_nao_como_resultado(session_factory, user, paint, monkeypatch):
    async def broken(self, query, *a, **k):
        raise ConnectionError("catálogo indisponível")
    monkeypatch.setattr("repositories.product.ProductRepository.search_by_name", broken, raising=False)
    monkeypatch.setattr("repositories.product.ProductRepository.search", broken, raising=False)
    out = await _run(session_factory, user, search_products_tool, {"query": "látex"})
    assert "error" in out and "products" not in out
