"""Twin (Darius): never converse with an automated counterpart.

Production fact (ids 12126-12158, contact 5511912362126): a bank auto-responder ("*Resposta Automática* ...
Fique atento a golpes e fraudes. Nao confirme dados") answered every twin reply, and the twin answered back
about once a minute: 12 outbound messages in 9 minutes. The loop guard only stopped it after 10 replies, and
then kept sending the holding message ("assistente automático do Dário") + an owner alert for EVERY further
bot message (12154-12158), so the alert did not interrupt the sequence.

Pure functions over Message-like rows (no DB, no settings).
"""

from __future__ import annotations

import re
import unicodedata

# Strong markers only. Anything weaker is left to the repetition rule below.
_MARKERS = (
    "resposta automatica",
    "resposta automatizada",
    "mensagem automatica",
    "mensagem automatizada",
    "mensagem gerada automaticamente",
    "atendimento automatico",
    "nao responda a esta mensagem",
    "nao responda esta mensagem",
    "auto-reply",
    "autoreply",
    "out of office",
    "nao confirme dados",
)

REPEAT_MIN_PRIOR = 2     # identical inbound texts already in history before the current one
MIN_REPEAT_LEN = 12      # ignore "ok", "bom dia"... a person can legitimately repeat those


def _val(x) -> str:
    return str(getattr(x, "value", x)).lower()


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[*_~`]", "", t)).strip()


def _fingerprint(text: str) -> str:
    return re.sub(r"\d+", "#", _norm(text))


def has_automation_marker(text: str) -> bool:
    n = _norm(text)
    return any(m in n for m in _MARKERS)


def is_automated_inbound(text: str, history, current_message_id: int | None = None) -> bool:
    """True when the inbound being answered looks machine-generated: it carries a strong marker, or the very
    same text (digits masked) already arrived REPEAT_MIN_PRIOR+ times from the contact in the history window."""
    if has_automation_marker(text):
        return True
    fp = _fingerprint(text)
    if len(fp) < MIN_REPEAT_LEN:
        return False
    prior = 0
    for r in history or ():
        if current_message_id is not None and getattr(r, "id", 0) >= current_message_id:
            continue
        if _val(r.direction) == "inbound" and _fingerprint(getattr(r, "content", "") or "") == fp:
            prior += 1
    return prior >= REPEAT_MIN_PRIOR
