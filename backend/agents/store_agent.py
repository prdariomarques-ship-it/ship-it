from agents.base import BaseAgent
from agents.tools.base import Tool
from agents.tools.communication import find_contact_tool, search_memory_tool, store_memory_tool
from agents.tools.domain import add_store_customer_tool, list_store_customers_tool


class StoreAgent(BaseAgent):
    """Produtos, pedidos, clientes, estoque e orçamentos."""

    @property
    def name(self) -> str:
        return "store"

    @property
    def description(self) -> str:
        return "Loja: produtos, pedidos, clientes, estoque e orçamentos."

    @property
    def system_prompt(self) -> str:
        return (
            "Você é o assistente comercial da loja do Dario dentro do Dario OS. "
            "Você ajuda com produtos, pedidos, cadastro de clientes, controle de estoque "
            "e elaboração de orçamentos. Tom profissional e cordial. Para orçamentos, "
            "apresente itens, quantidades, valores unitários e total de forma organizada. "
            "Use as ferramentas para consultar e cadastrar clientes reais."
        )

    @property
    def tools(self) -> list[Tool]:
        return [
            list_store_customers_tool,
            add_store_customer_tool,
            find_contact_tool,
            search_memory_tool,
            store_memory_tool,
        ]
