"""Twin (Darius): never speak for the owner about money movements.

Production facts:
  * 12198 (auto=t, contact 9): "Vc quer que eu baixe 50k no Aki, é isso? Me confirma ... antes de eu mexer."
    The twin offered to execute an operation, inferred from history, answering the inbound texts "Oie"/"Baixo".
  * 12134 (auto=t, contact 20): "Sobre o resgate, é isso: cai na segunda ... o movimento em si já tá fechado."
    The twin restated redemption status/dates as if it were the owner's own information.
  * 12109 "É essa mesma. Pode seguir." authorised something in a financial thread.

Output-side guard (like twin_output_guard): the generated reply is withheld when it commits to, confirms or
states the status of a money operation. Kill switch: environment TWIN_FINANCE_GUARD=0.
Pure function; no DB, no settings.
"""

from __future__ import annotations

import os
import re
import unicodedata

_AMOUNT = re.compile(r"r\$\s?\d|\b\d+(?:[.,]\d+)?\s?(?:k|mil|mi|milhao|milhoes|reais)\b")
# HIGH: investment-operation vocabulary; any mention in a reply is withheld (12134, 12206 "não precisa resgatar nada").
_HIGH = re.compile(r"resgat|boleta|aplicac|aplicar|aplicad|liquidar|liquidacao|cotiza")
# MEDIUM: everyday words (pix, saldo...) only count with an amount or a commitment ("manda o pix do almoço" passes).
_OPERATION = re.compile(r"transfer|\bpix\b|\bted\b|deposit|\bsaque\b|\bsacar\b|\bsaldo\b|\bextrato\b")
_MONEY_VERB = re.compile(r"\bbaix(?:a|ar|e|ei|o)\b|\bcompr(?:a|ar|ei|e)\b|\bvend(?:a|er|i|o)\b|\bpag(?:ar|uei|o)\b|\bmov(?:er|i|imento)\b")
_COMMIT = re.compile(
    r"antes de eu mexer|\bja fiz\b|\bja foi\b|\bfechad[oa]\b|\bcai na\b|\bcai em\b|\bvou (?:baixar|resgatar|transferir|aplicar|comprar|vender|mexer|pagar|mandar)\b"
    r"|\bpode seguir\b|\bpode fazer\b|\bautorizo\b|\bconfirmo\b|\bconfirmado\b")
_STRONG_COMMIT = re.compile(r"antes de eu mexer|\bpode seguir\b|\bpode fazer\b|\bautorizo\b|\bconfirmo\b|\bconfirmado\b|\bja fiz\b")


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    return re.sub(r"\s+", " ", "".join(c for c in t if not unicodedata.combining(c)).lower()).strip()


def reply_commits_money_operation(reply: str, context: str = "") -> str | None:
    """Reason string when `reply` commits to / confirms / reports the status of a money operation, else None.
    `context` = recent conversation text (used only to qualify a bare 'pode seguir' / 'confirmo')."""
    if os.environ.get("TWIN_FINANCE_GUARD", "1") == "0":
        return None
    r, c = _norm(reply), _norm(context)
    if not r:
        return None
    if _HIGH.search(r):
        return "operação de investimento na resposta"
    amount, operation = bool(_AMOUNT.search(r)), bool(_OPERATION.search(r))
    verb, commit = bool(_MONEY_VERB.search(r)), bool(_COMMIT.search(r))
    if operation and (amount or commit):
        return "operação financeira na resposta"
    if verb and amount:
        return "valor + movimentação na resposta"
    if _STRONG_COMMIT.search(r) and (_HIGH.search(c) or _OPERATION.search(c) or _AMOUNT.search(c)):
        return "confirmação em conversa financeira"
    return None
