"""O que o Gêmeo NÃO pode dizer em nome do dono, qualquer que seja o assunto (puro, sem I/O).

Casos reais (16 a 23/10/2026): "Pode emitir"/"Pode ser 10." a um robô de cobrança (14047, 14061); pedido de agência, conta e CPF a um cliente
(14519, 14549); "quero o reembolso" a quem não devia nada (13481, 13483: o dono dissera "5 mil" de SEGUIDORES); "tá ok" a um depósito sem comprovante
(15267); prazo assumido ("até amanhã já monto a base", 14563); ação impossível ("Já segui aqui", 14765).

Isto NÃO bloqueia assunto (o portão de risco decidiu que "financeiro" é tema, não bloqueio): bloqueia o ATO -- autorizar, cobrar, pedir dado bancário,
confirmar dinheiro, prometer entrega com prazo, afirmar que fez algo que um robô não faz. Na dúvida, a resposta vira a retenção neutra + alerta ao dono.
"""

import os
import re
import unicodedata
from typing import NamedTuple


def normalize_text(text: str) -> str:
    """minusculas, sem acento, espacos colapsados (local de proposito: o modulo nao depende de nenhum outro do Gemeo)."""
    stripped = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", stripped).strip()


def action_guard_enabled() -> bool:
    """Interruptor por ambiente, como os guardas de producao: TWIN_ACTION_GUARD=0 desliga."""
    return os.environ.get("TWIN_ACTION_GUARD", "1").strip().lower() not in {"0", "false", "no", "off"}


class Blocked(NamedTuple):
    category: str
    snippet: str


def _p(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


_BANK_DATA = _p(r"\b(?:agencia|conta\s+corrente|numero\s+da\s+conta|chave\s+pix|cpf|cnpj|dados\s+bancarios)\b")
_ASKING = _p(r"\b(?:manda|mande|envia|envie|passa|passe|informa|informe|confirma|confirme|me\s+da|preciso\s+d[aeo]s?)\b")
_CPF_NUMBER = _p(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_AUTHORIZE = _p(
    r"\b(?:pode\s+(?:emitir|gerar|aprovar|fechar|confirmar|pagar|transferir|depositar|assinar|cancelar)|aprovado|aprovo|autorizo|autorizado|"
    r"confirmo\s+(?:o\s+|a\s+)?(?:pagamento|acordo|pedido|compra|reuniao|cancelamento)|pode\s+ser\s+(?:a\s+)?opcao\s+\d+|pode\s+ser\s+\d{1,2}(?!\s*(?:h\b|hora|min|dia|reais|r\$|de\s)))\b"
)
_CHARGE = _p(r"\b(?:reembolso|estorno|quero\s+meu\s+dinheiro|nao\s+quitou|devolv\w+\s+(?:o\s+)?dinheiro)\b")
_MONEY_WORD = _p(r"\b(?:deposit\w*|pagou|pagamento|transferi\w*|comprovante)\b")
_MONEY_OK = _p(r"\b(?:ta\s+ok|esta\s+ok|tudo\s+certo|confirmado|recebi)\b")
_COMMIT_VERB = _p(r"\b(?:vou|ja|te|lhe)\s+(?:\w+\s+)?(?:monto|montar|organizar|organizo|formalizar|formalizo|enviar|envio|mandar|mando|passar|passo|retorno|retornar)\b")
_TIME = _p(r"\b(?:ate\s+(?:amanha|hoje|segunda|terca|quarta|quinta|sexta|sabado|domingo|as\s+\d)|amanha|hoje\s+ainda|ainda\s+hoje|em\s+\d+\s+(?:min|hora|dia)\w*)\b")
_FAKE_ACTION = _p(r"\bja\s+(?:segui|curti|compartilhei|salvei|assinei|paguei|transferi|depositei|emiti|cadastrei|agendei)\b|\bvou\s+seguir\b")
_FILLER = _p(r"^(?:ate|abraco|valeu|ok|tmj)\b")


def blocked_action(reply: str) -> Blocked | None:
    """(categoria, trecho) se a resposta pratica um ato proibido ao Gêmeo; None se pode seguir."""
    text = normalize_text(reply or "")
    if _CPF_NUMBER.search(text):
        return Blocked("dado_bancario", "cpf_ou_cnpj")
    m = _BANK_DATA.search(text)
    if m and _ASKING.search(text):
        return Blocked("dado_bancario", m.group(0))
    for category, pattern in (("autorizacao", _AUTHORIZE), ("cobranca", _CHARGE), ("acao_inventada", _FAKE_ACTION)):
        m = pattern.search(text)
        if m:
            return Blocked(category, m.group(0))
    if _MONEY_WORD.search(text) and (m := _MONEY_OK.search(text)):
        return Blocked("confirmacao_financeira", m.group(0))
    if (m := _COMMIT_VERB.search(text)) and _TIME.search(text) and len(text.split()) > 6:
        return Blocked("prazo", m.group(0))
    return None
