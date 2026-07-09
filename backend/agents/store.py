from agents.base import BaseAgent


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
            "e elaboração de orçamentos. Responda em português brasileiro, com tom "
            "profissional e cordial. Para orçamentos, apresente itens, quantidades, "
            "valores unitários e total de forma organizada."
        )
