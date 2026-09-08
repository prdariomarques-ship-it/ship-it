from agents.base import BaseAgent
from agents.registry import register_agent
from agents.tools.base import Tool
from agents.tools.communication import (
    find_contact_tool,
    search_memory_tool,
    store_memory_tool,
    update_contact_preference_tool,
)
from agents.tools.domain import (
    add_store_customer_tool,
    create_quote_tool,
    list_products_tool,
    list_store_customers_tool,
    record_order_tool,
    search_products_tool,
    update_store_customer_segment_tool,
)


@register_agent
class StoreAgent(BaseAgent):
    """Agente comercial da Oficina das Tintas (Marquescolor): catálogo,
    orçamento, pedido, cliente e qualificação de lead.

    NOTA (governança): ARCHITECTURE_FINAL.md classifica este agente como
    "migra para business/agents/ quando Business v1 for construído", com
    `store_customers` como seed literal de `Client`. As tabelas do módulo
    Business (`clients`/`deals`/`followups`) já foram migradas no banco em
    12/07 mas não têm model/repo/agente -- ver MODULE_CATALOG.md. Este
    agente foi deliberadamente mantido em Core (não migrado) por decisão
    explícita do produto: entregar o agente de vendas rápido, sem abrir a
    frente arquitetural do primeiro módulo de plataforma. Ver conversa de
    2026-09-08.
    """

    @property
    def name(self) -> str:
        return "store"

    @property
    def description(self) -> str:
        return "Comercial: catálogo, orçamento, pedido, cliente e qualificação de lead."

    @property
    def system_prompt(self) -> str:
        return (
            "Você é o agente comercial da Oficina das Tintas (Marquescolor) dentro "
            "do Dario OS -- atende clientes de tintas e materiais de construção "
            "pelo WhatsApp. Tom profissional, cordial e direto.\n\n"
            "Fluxo esperado de uma conversa de venda:\n"
            "1. Identifique o cliente (find_contact / list_store_customers) ou "
            "cadastre um novo (add_store_customer) antes de seguir.\n"
            "2. Assim que der para perceber o perfil dele na conversa, classifique "
            "com update_store_customer_segment: 'pintor' (compra recorrente, preço "
            "por volume), 'lojista' (revenda) ou 'consumidor_final' (uma compra, "
            "orientação de uso). Isso direciona o tom e a negociação.\n"
            "3. Para consultar produtos e preços reais, use search_products ou "
            "list_products -- nunca invente nome, preço ou SKU de produto.\n"
            "4. Para montar um orçamento, use create_quote com os itens (sku + "
            "quantidade); apresente ao cliente item por item, com preço unitário e "
            "total, de forma organizada.\n"
            "5. Só depois que o cliente confirmar a compra, use record_order -- isso "
            "grava o pedido no histórico do cliente e baixa o estoque. Nunca chame "
            "record_order sem confirmação explícita do cliente.\n\n"
            "Se um produto não existir no catálogo ou o estoque for insuficiente, "
            "diga isso claramente ao cliente em vez de prometer o que não pode "
            "cumprir."
        )

    @property
    def tools(self) -> list[Tool]:
        return [
            list_store_customers_tool,
            add_store_customer_tool,
            update_store_customer_segment_tool,
            list_products_tool,
            search_products_tool,
            create_quote_tool,
            record_order_tool,
            find_contact_tool,
            search_memory_tool,
            store_memory_tool,
            update_contact_preference_tool,
        ]
