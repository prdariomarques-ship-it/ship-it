"""Blocos extras de contexto do Twin (alem do manual e do historico).

Hoje: exemplos de estilo aprendidos das respostas reais do dono (`services/style_distill.py`).
Melhor esforco: qualquer falha aqui devolve lista vazia, nunca impede nem atrasa a resposta do Twin.
"""

from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

STYLE_HEADER = (
    "Exemplos reais de como o Dário respondeu a mensagens parecidas. Use SOMENTE para imitar a cadência "
    "(tamanho, tom, vocabulário). São exemplos, não fatos: não repita nomes, números, valores, datas ou "
    "informações de nenhuma pessoa que apareça neles, e não copie uma resposta inteira."
)


def format_style_block(examples: list[str]) -> str:
    return STYLE_HEADER + "\n\n" + "\n\n".join(f"Exemplo {number}:\n{text}" for number, text in enumerate(examples, 1))


async def build_twin_extra_system(message_text: str, instance: str) -> list[str]:
    settings = get_settings()
    if not settings.style_examples_enabled:
        return []
    try:
        from services.style_distill import retrieve_style_examples

        examples = await retrieve_style_examples(message_text, instance)
    except Exception:  # noqa: BLE001 - estilo e opcional; o Twin responde sem ele
        logger.warning("Exemplos de estilo indisponiveis; o Twin segue sem eles", exc_info=True)
        return []
    return [format_style_block(examples)] if examples else []
