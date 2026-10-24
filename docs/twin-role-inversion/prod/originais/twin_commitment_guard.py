"""Commitment guard for the digital twin: a generated reply must not commit the OWNER to anything.

Production facts: the twin promised follow-ups and presence in the owner's name ("Deixa eu confirmar com quem
cuida disso e te retorno" 12232, "Assim que eu tiver a resposta te falo" 12234, "Deixa eu falar com ele e ver o
que dá" 12211 -- contradicted by the owner's own audio minutes later --, "Estou entrando sim" 12212) and
accepted schedules (12050, 12071). The twin cannot keep any of those promises.

`reply_makes_commitment(reply)` -> short label of the first commitment found, or None. A hit sends the reply
through the existing risk path (silent hold + owner alert with the blocked draft). Kill-switch: TWIN_COMMITMENT_GUARD=0.

Pure, stdlib only; accent- and case-insensitive. Deliberately conservative about WHAT counts: future-tense
promises, follow-up promises, presence/attendance and accepted date+time. Plain acknowledgements ("combinado",
"beleza", "valeu") are not commitments.
"""

from __future__ import annotations

import os
import re
import unicodedata

_HOUR = r"(?:\d{1,2}\s*h(?:\d{2})?|\d{1,2}:\d{2}|\d{1,2}\s*horas?)"
_DAY = r"(?:hoje|amanha|depois\s+de\s+amanha|segunda|terca|quarta|quinta|sexta|sabado|domingo|semana\s+que\s+vem|proxima\s+semana)"
_ACCEPT = r"(?:pode\s+ser|fechado|combinado|confirmado|confirmo|marcado|agendado|beleza|ok|tranquilo|perfeito|certo|otimo)"

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(rx))
    for label, rx in (
        ("promessa de retorno",
         r"\bte\s+(?:retorno|retorna|aviso|falo|passo|mando|envio|ligo|chamo|confirmo|respondo|encaminho|apresento|procuro)\b"
         r"|\bretorno\s+(?:pra|para)\s+(?:voce|vc|ti)\b|\bja\s+volto\b|\bvolto\s+(?:a\s+te\s+)?(?:falar|responder)\b"
         r"|\bassim\s+que\s+(?:eu\s+)?(?:tiver|souber|puder|conseguir|chegar|sair|ver|resolver)\b"),
        ("promessa de ação",
         r"\bdeixa\s+eu\s+(?:confirmar|conferir|verificar|checar|falar|consultar|alinhar|resolver|perguntar|ligar)\b"
         r"|\bdeixe-?me\s+(?:confirmar|conferir|verificar|checar|falar|consultar|alinhar)\b"
         r"|\bvou\s+(?:confirmar|conferir|verificar|checar|falar\s+com|consultar|alinhar|resolver|providenciar|marcar|agendar"
         r"|ligar|passar\s+(?:pra|para)|enviar|mandar|encaminhar|ver\s+o\s+que|dar\s+uma\s+olhada|cuidar)\b"),
        ("presença/comparecimento",
         r"\b(?:estou|to|ja\s+estou|ja\s+to)\s+(?:entrando|chegando|indo|saindo|a\s+caminho|no\s+caminho|em\s+casa|chegando\s+(?:ai|la|em\s+casa))\b"
         r"|\bja\s+(?:chego|saio|to\s+saindo)\b|\bchego\s+(?:ja|logo|em\s+\d+)\b|\bsaio\s+(?:ja|agora|em\s+\d+)\b"
         r"|\bvou\s+(?:la|pra\s+ai|para\s+ai|passar\s+ai|passar\s+la|participar|comparecer|estar\s+(?:ai|la|presente))\b"
         r"|\bestarei\b|\bconfirmo\s+(?:minha\s+)?presenca\b|\bpode\s+contar\s+comigo\b|\bnos\s+vemos\s+(?:la|ai|amanha|hoje)\b"
         r"|\bte\s+(?:espero|vejo)\s+(?:la|ai|amanha|hoje)\b"),
        ("horário/agenda aceito",
         rf"\b{_ACCEPT}\b.{{0,40}}\b(?:as|a)?\s*{_HOUR}"
         rf"|\b{_DAY}\b.{{0,30}}\b(?:as|a)?\s*{_HOUR}"
         rf"|\b{_HOUR}\b.{{0,30}}\b{_DAY}\b"),
    )
)


def _normalise(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", stripped)


def reply_makes_commitment(reply: str | None) -> str | None:
    if os.environ.get("TWIN_COMMITMENT_GUARD", "1").strip().lower() in {"0", "false", "no", "off"}:
        return None
    if not reply or not reply.strip():
        return None
    text = _normalise(reply)
    for label, pattern in _PATTERNS:
        if pattern.search(text):
            return label
    return None
