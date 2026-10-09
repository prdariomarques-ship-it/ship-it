"""Risk gate for the digital twin ("Darius"): decides whether an inbound
message may EVER receive a reply written in the owner's voice.

One category is off-limits for impersonation, always: personal or
spiritual crisis (the owner is a pastor -- someone in crisis must never get
a synthetic "me"). A hit means: neutral holding message + a separate alert
to the owner.

Financial/wealth topics used to gate too (the owner is a registered wealth
manager -- a client's investment question used to always go to him, never a
model). Per his explicit decision on 2026-09-21 -- made after being told
this removes a compliance safeguard around investment guidance attributed
to a licensed advisor -- the twin now answers financial questions directly,
same as any other topic. `classify_text` still labels "financeiro" text
(kept for Fase 2 / future analytics use) but `is_high_risk_for_impersonation`
no longer escalates on that category -- only "crise" still blocks
impersonation.

Design rule: RECALL over PRECISION for what remains gated (crisis). A false
positive costs one message the owner answers himself; a false negative is
an impersonated answer to someone in crisis. Patterns are therefore broad
on purpose, run over accent-stripped lowercase text (people type
"nao"/"separacao" quickly), and cover the recent conversation, not just the
last message -- "ok, pode ser" is still part of a sensitive thread.

2026-10-08 revision -- this module used to take bare strings for
`recent_history` and return just (bool, str). Two incidents forced a
change, not a loosening of recall:

  - A denial ("a culpa nao e nossa", the owner's own outbound audio
    transcript) sat in history and kept re-triggering "crise" on every
    later message in the same conversation, because a bare keyword match
    has no concept of negation.
  - "Separar os produtos" (a store-inventory question) matched the same
    pattern as a personal separation/divorce, because the category has no
    concept of business context, same reasoning as the existing
    _is_informational_repass exception for "negocio".

Both are now narrow, auditable exceptions over the SAME broad term lists --
nothing was removed from the lists themselves. Callers get a structured
RiskEvidence (message id, direction, timestamp, matched snippet, category)
instead of a bare reason string, so a human reviewing an alert can see
exactly what triggered it without re-reading the whole conversation.

Fase 2 (style distillation) reuses `classify_text` so the corpus filter and
this gate's categorization share the exact same lists.
"""

# Fase 2: ver spec de destilacao de estilo (PARTE 2 do prompt do gemeo Darius) --
# job periodico "darius.distill_style", nao implementado ainda.

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import NamedTuple

_FLAGS = re.IGNORECASE

# Written WITHOUT accents: input is normalized by `normalize_text` first.
_FINANCIAL_TERMS: tuple[str, ...] = (
    r"invest\w*",
    r"acao",
    r"acoes",
    r"carteira\w*",
    r"aportes?",
    r"aportar",
    r"patrimoni\w*",
    r"aplica(?:r|cao|coes)",
    r"aplicad\w+",
    r"resgat\w*",
    r"fundos?",
    r"renda\s+(?:fixa|variavel)",
    r"bolsa",
    r"corretora\w*",
    r"emprestimo\w*",
    r"divida\w*",
    r"imposto\s+de\s+renda",
    r"irpf",
    r"previdencia\w*",
    r"cdb",
    r"lci",
    r"lca",
    r"tesouro\s+(?:direto|selic|ipca|prefixado)",
    r"selic",
    r"dividendos?",
    r"rentabilidade",
    r"rendimentos?",
    r"juros",
    r"cotas?",
    r"etfs?",
    r"fiis?",
    r"cripto\w*",
    r"bitcoin",
    r"cambio",
    r"dolar",
    r"heranca",
    r"inventario",
    r"holding",
    r"financiamento\w*",
    r"consorcio",
    r"credito",
    r"portfolio",
    r"alocacao",
    r"multimercado",
    r"debenture\w*",
    r"cri",
    r"cra",
)

# Business-sale / ownership-change terms -- kept as their own category, NOT
# folded into "financeiro" (which stopped escalating on 2026-09-21; see the
# module docstring). Negotiating the sale/handover of the store is a
# different kind of decision than an investment question -- the owner's
# 2026-09-21 decision was about investment advice specifically, and this
# category is what caught the Erika Soares incident that same review (a
# contact negotiating the store's sale/handover got 6 turns of scheduling
# from the twin before Dario stepped in manually).
_BUSINESS_TERMS: tuple[str, ...] = (
    r"venda\w*",
    r"vend(?:er|endo|eu|i|emos|eram)",
    r"repass\w*",
    r"comprador\w*",
)

_CRISIS_TERMS: tuple[str, ...] = (
    r"suicid\w*",
    r"me\s+matar",
    r"quero\s+morrer",
    r"nao\s+quero\s+mais\s+viver",
    r"nao\s+aguento\s+mais",
    r"acabar\s+com\s+(?:tudo|minha\s+vida)",
    r"tirar\s+minha\s+vida",
    r"depress\w*",
    r"crises?",
    r"socorro",
    r"desesper\w*",
    r"abus(?:o|ad\w*|ei|ou)",
    r"separa(?:cao|coes|r|do|da|mos)",
    r"divorci\w*",
    r"luto",
    r"morreu",
    r"faleceu",
    r"falecimento",
    r"velorio",
    r"enterro",
    r"internad\w*",
    r"automutil\w*",
    r"se\s+cortar",
    r"ansiedade",
    r"ansios\w*",
    r"angusti\w*",
    r"sem\s+(?:saida|esperanca)",
    r"panico",
    r"traicao",
    r"traiu",
    r"violencia",
    r"agredi\w*",
    r"agressao",
    r"vicio",
    r"overdose",
    r"cancer",
    r"diagnostic\w*",
    r"perdi\s+(?:meu|minha)",
    # Vulnerabilidade emocional e pedido pastoral: sem palavra de "crise", mas
    # quem escreve assim espera o Dario de verdade, nao uma imitacao.
    r"cansad\w*",
    r"esgotad\w*",
    r"exaust\w*",
    r"estress\w*",
    r"sobrecarreg\w*",
    r"desanim\w*",
    r"triste\w*",
    r"choran\w*",
    r"chorei",
    r"chorar",
    r"solidao",
    r"sozinh\w*",
    r"medo",
    r"culpa",
    r"vazio",
    r"sem\s+sentido",
    # NOT "oracao"/"orar"/"ore por": per the owner's 2026-09-21 decision the
    # twin now writes a short prayer directly when asked (see
    # agents/prompts/darius_twin.md) instead of escalating every prayer
    # request -- "uma palavra" (wanting pastoral guidance/a word, a broader
    # ask than just a prayer) still escalates.
    r"uma\s+palavra",
    r"desabaf\w*",
    r"aconselh\w*",
    r"preciso\s+(?:de\s+ajuda|conversar|desabafar)",
    # Medical emergency, self or third-party (2026-09-21 review: "ele passou
    # mal" -- a contact reporting someone else's medical episode -- got only
    # a clarifying question from the twin, never an escalation).
    r"passou\s+mal",
    r"passar\s+mal",
    r"mal[- ]estar",
    r"desmai\w*",
    r"infarto",
    r"avc",
    r"emergencia",
    r"pronto[- ]socorro",
    r"ambulancia",
    r"internou",
)


def _compile(terms: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(terms) + r")(?![a-z0-9])", _FLAGS)


FINANCIAL_PATTERN = _compile(_FINANCIAL_TERMS)
BUSINESS_PATTERN = _compile(_BUSINESS_TERMS)
CRISIS_PATTERN = _compile(_CRISIS_TERMS)

# Paraphrase grouping for incident deduplication (orchestrator/incident_dedup.py):
# several _CRISIS_TERMS entries are just different ways of saying the SAME
# underlying thing (crying: "chorei"/"chorar"/"choran*"; suicidal ideation:
# "quero morrer"/"acabar com minha vida"/"suicid*"...). Treating each
# matched snippet as independently "new evidence" would re-alert on a bare
# rewording of the same statement. Treating two DIFFERENT groups as
# equivalent would hide a real escalation (e.g. "culpa" -> "quero morrer").
# This mapping only ever COLLAPSES entries that are already in
# _CRISIS_TERMS as separate alternatives for the same concept -- it adds no
# new matching behavior and removes nothing from the broad lists above.
# A snippet whose pattern is not listed here falls back to itself in
# group_for_snippet (never silently merged with anything else), which is
# the same "recall over precision" bias as the rest of this module: when
# unsure whether two snippets are the same evidence, treat them as
# different and allow the re-alert.
_CRISIS_TERM_GROUPS: tuple[tuple[str, str], ...] = (
    ("suicidio_ideacao", r"suicid\w*"),
    ("suicidio_ideacao", r"me\s+matar"),
    ("suicidio_ideacao", r"quero\s+morrer"),
    ("suicidio_ideacao", r"nao\s+quero\s+mais\s+viver"),
    ("suicidio_ideacao", r"acabar\s+com\s+(?:tudo|minha\s+vida)"),
    ("suicidio_ideacao", r"tirar\s+minha\s+vida"),
    ("falecimento", r"morreu"),
    ("falecimento", r"faleceu"),
    ("falecimento", r"falecimento"),
    ("velorio", r"velorio"),
    ("velorio", r"enterro"),
    ("automutilacao", r"automutil\w*"),
    ("automutilacao", r"se\s+cortar"),
    ("ansiedade", r"ansiedade"),
    ("ansiedade", r"ansios\w*"),
    ("ansiedade", r"angusti\w*"),
    ("traicao", r"traicao"),
    ("traicao", r"traiu"),
    ("violencia", r"violencia"),
    ("violencia", r"agredi\w*"),
    ("violencia", r"agressao"),
    ("exaustao", r"cansad\w*"),
    ("exaustao", r"esgotad\w*"),
    ("exaustao", r"exaust\w*"),
    ("exaustao", r"estress\w*"),
    ("exaustao", r"sobrecarreg\w*"),
    ("tristeza", r"desanim\w*"),
    ("tristeza", r"triste\w*"),
    ("choro", r"choran\w*"),
    ("choro", r"chorei"),
    ("choro", r"chorar"),
    ("solidao", r"solidao"),
    ("solidao", r"sozinh\w*"),
    ("pedido_pastoral", r"uma\s+palavra"),
    ("pedido_pastoral", r"desabaf\w*"),
    ("pedido_pastoral", r"aconselh\w*"),
    ("pedido_pastoral", r"preciso\s+(?:de\s+ajuda|conversar|desabafar)"),
    ("emergencia_medica", r"passou\s+mal"),
    ("emergencia_medica", r"passar\s+mal"),
    ("emergencia_medica", r"mal[- ]estar"),
    ("emergencia_medica", r"desmai\w*"),
    ("emergencia_medica", r"infarto"),
    ("emergencia_medica", r"avc"),
    ("emergencia_medica", r"emergencia"),
    ("emergencia_medica", r"pronto[- ]socorro"),
    ("emergencia_medica", r"ambulancia"),
    ("emergencia_medica", r"internou"),
)
_CRISIS_TERM_GROUP_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (group, re.compile(pattern, _FLAGS)) for group, pattern in _CRISIS_TERM_GROUPS
)


def group_for_snippet(snippet: str) -> str:
    """Canonical paraphrase group for a matched _CRISIS_TERMS snippet, or
    the snippet itself if it is not part of any defined group (see the
    comment above _CRISIS_TERM_GROUPS for why an unknown snippet is never
    merged with anything)."""
    for group, pattern in _CRISIS_TERM_GROUP_PATTERNS:
        if pattern.fullmatch(snippet):
            return group
    return snippet

# Categories that still block impersonation -- see is_high_risk_for_impersonation.
_ESCALATING_CATEGORIES = frozenset({"crise", "negocio"})


def normalize_text(text: str) -> str:
    """Lowercase, accent-stripped, whitespace-collapsed (ç -> c, ã -> a...)."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped.lower()).strip()


# Exceções restritas ao compartilhamento de endereço.
_INFORMATIONAL_REPASS_PATTERNS = (
    re.compile(
        r"(?<!\w)(?P<verb>repassar) o endereco(?: da igreja)?"
        r"(?=(?:[.!?]+(?:\s|$)|$))"
    ),
    re.compile(
        r"(?<!\w)sobre o endereco da igreja, voce quer pra saber como chegar "
        r"ou pra (?P<verb>repassar) pra outra pessoa\?"
    ),
)


def _is_informational_repass(normalized: str, hit: re.Match[str]) -> bool:
    if hit.group(0) != "repassar":
        return False
    return any(
        context.span("verb") == hit.span()
        for pattern in _INFORMATIONAL_REPASS_PATTERNS
        for context in pattern.finditer(normalized)
    )


# "Separar" matched against store-inventory language ("separar os produtos",
# "separar o pedido") is a different sense from a personal separation. Same
# shape as _is_informational_repass above: a narrow, auditable exception
# over the same broad term, not a removal from _CRISIS_TERMS.
_BUSINESS_SEPARATION_OBJECTS = (
    r"produtos?",
    r"item(?:ns)?",
    r"pedidos?",
    r"estoque",
    r"mercadorias?",
    r"encomendas?",
    r"compras?",
)
_BUSINESS_SEPARATION_PATTERN = re.compile(
    r"(?<!\w)separa(?:r|cao|do|da|mos)\s+(?:o|os|a|as)?\s*(?:"
    + "|".join(_BUSINESS_SEPARATION_OBJECTS)
    + r")(?!\w)"
)


def _is_business_separation(normalized: str, hit: re.Match[str]) -> bool:
    if not hit.group(0).startswith("separa"):
        return False
    return any(
        context.start() <= hit.start() and hit.end() <= context.end()
        for context in _BUSINESS_SEPARATION_PATTERN.finditer(normalized)
    )


# Negation governing the matched clause. Portuguese puts the negator on
# either side of the term depending on sentence shape:
#   - BEFORE, negating a verb the term is part of/follows directly:
#     "NAO tenho medo", "NUNCA senti culpa".
#   - AFTER, negating a copula that follows the noun: "a culpa NAO E nossa"
#     ("the blame is NOT ours") -- the negator trails the matched noun.
#
# Two corrections over the first version of this check (2026-10-08 review):
#
#   1. A negator must not be searched for past a clause boundary (comma,
#      period, semicolon, "!", "?"). Without this, "nao aguento mais, isso
#      nao e facil" wrongly cleared "nao aguento mais" -- that match's own
#      crisis signal has nothing to do with the SEPARATE, later clause
#      "isso nao e facil", which negates "facil" (easy), not the earlier
#      phrase. Proximity across a clause break is not grammatical binding.
#
#   2. A term that is ITSELF a negated idiom ("nao aguento mais", "nao
#      quero mais viver") must never be cancelled by this check at all.
#      "nao aguento" does not mean an absence of suffering -- quite the
#      opposite, it is the crisis signal, and its own "nao" is part of the
#      phrase's fixed meaning, not an external negator applied to it. Any
#      _CRISIS_TERMS entry that itself starts with a negator is exempt.
_NEGATORS = {"nao", "nunca", "jamais"}
_NEGATION_WINDOW_WORDS = 3
_CLAUSE_BREAK = re.compile(r"[.,;!?]")
_COPULA_VERBS = {"e", "eh", "foi", "foram", "sao", "era", "eram", "seja"}
_AFTER_NEGATION_PATTERN = re.compile(
    r"^\s*(?:\S+\s+){0,2}?(?:nao|nunca|jamais)\s+(?:" + "|".join(_COPULA_VERBS) + r")\b"
)
_SELF_NEGATING_TERM_PREFIXES = ("nao ", "nunca ", "jamais ")


def _clause_before(normalized: str, position: int) -> str:
    before = normalized[:position]
    boundary = max((m.end() for m in _CLAUSE_BREAK.finditer(before)), default=0)
    return before[boundary:]


def _clause_after(normalized: str, position: int) -> str:
    after = normalized[position:]
    match = _CLAUSE_BREAK.search(after)
    return after[: match.start()] if match else after


def _is_negated(normalized: str, hit: re.Match[str]) -> bool:
    if hit.group(0).startswith(_SELF_NEGATING_TERM_PREFIXES):
        return False
    before_words = _clause_before(normalized, hit.start()).split()[-_NEGATION_WINDOW_WORDS:]
    if any(word in _NEGATORS for word in before_words):
        return True
    return bool(_AFTER_NEGATION_PATTERN.match(_clause_after(normalized, hit.end())))


def _is_colloquial_no_worries(normalized: str, hit: re.Match[str]) -> bool:
    """"Sem crise" is a common colloquial reassurance ("no worries" / "no
    problem" -- e.g. "pode vir, sem crise"), not a crisis disclosure.

    This is deliberately its own narrow, immediately-adjacent check rather
    than adding "sem" to _NEGATORS: that set drives _is_negated's 3-word
    look-back window, and widening it would risk swallowing a genuine
    signal whenever "sem" happens to precede an unrelated word in the same
    window -- e.g. "sem conseguir mais, quero me matar" must still
    escalate. Requiring "sem" as the literal word immediately before
    "crise" avoids that."""
    if hit.group(0) != "crise":
        return False
    before = normalized[: hit.start()].split()
    return bool(before) and before[-1] == "sem"


def classify_text(text: str) -> tuple[str, str] | None:
    """(category, matched term) for the first hit that is not excluded by a
    narrow exception (informational address-sharing, business-inventory
    "separar", direct negation, or the colloquial "sem crise"), or None.
    Checked in order of urgency:
    crisis, then negocio (business-sale/ownership-change), then financeiro
    (investment topics -- classified but no longer escalating, see module
    docstring)."""
    normalized = normalize_text(text)
    for category, pattern in (
        ("crise", CRISIS_PATTERN),
        ("negocio", BUSINESS_PATTERN),
        ("financeiro", FINANCIAL_PATTERN),
    ):
        for match in pattern.finditer(normalized):
            if category == "negocio" and _is_informational_repass(normalized, match):
                continue
            if category == "crise" and _is_business_separation(normalized, match):
                continue
            if category == "crise" and _is_negated(normalized, match):
                continue
            if category == "crise" and _is_colloquial_no_worries(normalized, match):
                continue
            return category, match.group(0)
    return None


class MessageAuthor(str, Enum):
    """Who actually produced the text, as determined by the caller from
    message.direction / sent_by_human / is_autopilot_reply / whatsapp_instance
    -- this module never guesses authorship itself, it only consumes it."""

    CLIENT = "client"
    OWNER = "owner"
    BOT = "bot"
    UNKNOWN = "unknown"


class HistoryEntry(NamedTuple):
    """One turn of context for the risk gate. `text` is whatever the caller
    already resolved to show the model/classifier (e.g. handlers.py's
    `_owner_audio_history_content`, marker included) -- this module does not
    special-case that marker, it only needs to know who said it."""

    message_id: int
    author: MessageAuthor
    created_at: datetime | None
    text: str


@dataclass(frozen=True)
class RiskEvidence:
    """Traceable evidence for an escalation decision -- never just "a word
    matched somewhere in the conversation". `snippet` is the matched term
    only (e.g. "culpa"), never the full message."""

    category: str
    snippet: str
    source_message_id: int
    source_author: MessageAuthor
    source_created_at: datetime | None
    in_current_message: bool

    def reason(self) -> str:
        where = "na mensagem atual" if self.in_current_message else "no histórico recente"
        who = {
            MessageAuthor.CLIENT: "cliente",
            MessageAuthor.OWNER: "proprietário",
            MessageAuthor.BOT: "bot/automação",
            MessageAuthor.UNKNOWN: "autoria incerta",
        }[self.source_author]
        return f"{self.category}: '{self.snippet}' {where} (autor: {who}, msg {self.source_message_id})"


def is_high_risk_for_impersonation(
    current_message_id: int,
    current_text: str,
    recent_history: list[HistoryEntry],
) -> RiskEvidence | None:
    """Evidence for why impersonation must be blocked, or None. Only "crise"
    and "negocio" escalate (see _ESCALATING_CATEGORIES); "financeiro" is
    still classified but never returned here.

    The current message is always attributed to the client (the caller only
    reaches this gate for an inbound client message) and checked first.
    History entries carry their own author -- an owner- or bot-authored hit
    still returns evidence (the conversation thread still needs the
    context, per the module docstring's "ok, pode ser" example), but the
    evidence records who actually said it so a human reviewing the alert
    is not misled into thinking the client said it.
    """
    hit = classify_text(current_text)
    if hit and hit[0] in _ESCALATING_CATEGORIES:
        return RiskEvidence(
            category=hit[0],
            snippet=hit[1],
            source_message_id=current_message_id,
            source_author=MessageAuthor.CLIENT,
            source_created_at=None,
            in_current_message=True,
        )
    for entry in recent_history:
        hit = classify_text(entry.text)
        if hit and hit[0] in _ESCALATING_CATEGORIES:
            return RiskEvidence(
                category=hit[0],
                snippet=hit[1],
                source_message_id=entry.message_id,
                source_author=entry.author,
                source_created_at=entry.created_at,
                in_current_message=False,
            )
    return None
