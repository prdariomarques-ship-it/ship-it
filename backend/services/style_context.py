"""Exemplos de estilo para o prompt de um agente (Twin, Loja, B2B, Azusa), buscados SO na propria instancia.

Isolamento: a origem vetorial e `style_example:<instancia>`; um agente nunca ve exemplos de outra instancia (a Azusa continua
isolada). Uma instancia so participa se estiver em `STYLE_INSTANCES` (vazio = apenas a pessoal). Melhor esforco: qualquer falha
devolve lista vazia e o agente responde como antes.
"""

from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

HEADER_RULES = (
    "Use SOMENTE para imitar a cadência (tamanho, tom, vocabulário). São exemplos, não fatos: não repita nomes, números, valores, "
    "datas ou informações de nenhuma pessoa que apareça neles, e não copie uma resposta inteira. Preço, estoque, prazo, "
    "disponibilidade e qualquer dado do cliente vêm SOMENTE das ferramentas e da conversa, nunca dos exemplos."
)


def author_label(instance: str) -> str:
    return "o Dário" if instance == get_settings().evolution_personal_instance else "a equipe desta conta"


def format_style_block(examples: list[str], instance: str) -> str:
    from agents.darius_twin_roles import OTHER_CONVERSATION_NOTE, OWNER_FACTS_NOTE

    notes = OTHER_CONVERSATION_NOTE + (OWNER_FACTS_NOTE if instance == get_settings().evolution_personal_instance else "")
    header = f"Exemplos reais de como {author_label(instance)} respondeu a mensagens parecidas. {HEADER_RULES} {notes}"
    return header + "\n\n" + "\n\n".join(f"Exemplo {number}:\n{text}" for number, text in enumerate(examples, 1))


async def build_style_blocks(message_text: str, instance: str) -> list[str]:
    settings = get_settings()
    if not settings.style_examples_enabled or not instance:
        return []
    try:
        from services.style_distill import retrieve_style_examples, style_instances

        if instance not in style_instances():
            return []
        examples = await retrieve_style_examples(message_text, instance)
    except Exception:  # noqa: BLE001 - estilo e opcional; o agente responde sem ele
        logger.warning("Exemplos de estilo indisponiveis; o agente segue sem eles", exc_info=True)
        return []
    return [format_style_block(examples, instance)] if examples else []
