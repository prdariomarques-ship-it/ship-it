"""Papéis no contexto do Gêmeo: quem escreveu cada fala e de quem é o sujeito da conversa.

Por que existe (caso "Gerente LIBINA", msg 15424): o contato perguntou ao dono se ele tinha melhorado. O Gêmeo respondeu pelo dono
("Ainda não, tô na mesma. Febre não baixou...") e depois devolveu "Vc tá melhorando aí?" como se o contato estivesse doente. Duas causas no
contexto montado para o modelo:
  1. o histórico rotulava todo OUTBOUND como `assistant`, misturando o que o dono digitou com o que o próprio Gêmeo respondeu;
  2. os exemplos de outras conversas (`services/style_context.py`) entravam sem dizer que a "Pergunta" é de OUTRA pessoa, e o prompt
     nunca dizia quem é o sujeito de "você melhorou?" (o dono).

Este módulo é puro (sem I/O, sem LLM): rotula a autoria, guarda a regra de papéis em texto e aplica uma rede de segurança determinística
sobre a resposta. A rede existe porque instrução em prompt não é garantia: se o modelo ainda devolver a pergunta de saúde a quem não disse
estar doente, a frase é removida. Fatos sobre o próprio dono NÃO são tocados, de onde quer que venham.
"""

import re
from collections.abc import Callable, Iterable

from models.message import MessageDirection
from providers.llm.base import ChatMessage

OWNER_LABEL = "[Dário]"
TWIN_LABEL = "[Gêmeo]"

ROLE_RULES = (
    "Papéis na conversa (regra fixa): quem escreve para você é o interlocutor; quem responde é o Dário, ou seja, você. "
    "Quando o interlocutor pergunta \"você melhorou?\", \"tá melhor?\", \"como você está?\", a pergunta é SOBRE O DÁRIO: responda sobre ele. "
    "Não devolva pergunta sobre a saúde do interlocutor (\"e você, melhorou?\") a menos que ELE tenha dito, nesta conversa, que está doente ou mal. "
    f"No histórico, as falas de quem responde vêm marcadas: {OWNER_LABEL} foi o próprio Dário que digitou; {TWIN_LABEL} foi um assistente automático "
    "falando em nome dele. Fale sempre como o Dário e NUNCA escreva esses marcadores na resposta. "
    "O nome ou apelido com que o interlocutor chama você (Netinho, pastor X, \"pai\") é o SEU: nunca use esse nome para falar com ele. "
    "Não afirme como você está, onde está nem o que já fez (\"tô bem\", \"tomei\", \"já fiz\", \"já segui\") se isso não estiver na conversa; "
    "diga que confirma depois. Nunca autorize, aprove, emita, cobre, peça agência/conta/CPF nem assuma prazo: isso é só do Dário. "
    "Trechos de exemplo (se houver) são de OUTRAS conversas do Dário com OUTRAS pessoas: o interlocutor atual não é nenhuma delas e nada ali "
    "descreve a situação dele. Fatos sobre o próprio Dário que aparecem nesses trechos (como a saúde dele) continuam valendo quando perguntarem sobre ele."
)

CONTACT_NOT_OWNER = " Essa pessoa NÃO é o Dário: o que ela diz é sobre ela, e o que ela pergunta sobre \"você\" é sobre o Dário."

OTHER_CONVERSATION_NOTE = (
    "Cada exemplo abaixo é de OUTRA conversa: a Pergunta foi feita por outra pessoa e a Resposta foi dada a essa pessoa. "
    "Nada neles descreve o interlocutor atual (saúde, situação, pedidos)."
)
OWNER_FACTS_NOTE = " Exceção: fatos sobre o próprio Dário que aparecem na Resposta (por exemplo, como ele está de saúde) podem ser usados quando perguntarem sobre ele."


def author_of(row: object) -> str | None:
    """'twin' | 'owner' | None (entrada, ou saída sem origem registrada). Mesma ordem do `_author_of` do handler: autopiloto vence."""
    if getattr(row, "direction", None) != MessageDirection.OUTBOUND:
        return None
    if getattr(row, "is_autopilot_reply", False):
        return "twin"
    if getattr(row, "sent_by_human", False):
        return "owner"
    return None


def build_twin_history(
    rows: Iterable[object], *, content_of: Callable[[object], str | None], exclude_id: int | None = None,
) -> list[ChatMessage]:
    """Histórico para o LLM. Entrada = `user` (o interlocutor). Saída = `assistant`, marcada com [Dário] ou [Gêmeo] quando a autoria é
    conhecida; sem origem registrada fica como sempre foi (nunca se adivinha a autoria)."""
    history: list[ChatMessage] = []
    for row in rows:
        content = content_of(row)
        if not content or getattr(row, "id", None) == exclude_id:
            continue
        if getattr(row, "direction", None) == MessageDirection.INBOUND:
            history.append(ChatMessage(role="user", content=content))
            continue
        label = {"owner": OWNER_LABEL, "twin": TWIN_LABEL}.get(author_of(row) or "")
        history.append(ChatMessage(role="assistant", content=f"{label} {content}" if label else content))
    return history


_MARKER = re.compile(r"(?m)^[ \t]*\[(?:Dário|Dario|Gêmeo|Gemeo)\][ \t]*")


def strip_author_markers(reply: str) -> str:
    """O modelo pode imitar o marcador do histórico; ele nunca vai ao contato."""
    return _MARKER.sub("", reply).strip()


# --- rede de segurança: pergunta de saúde devolvida a quem não disse estar doente ---------------------------------------------------

_ASKS_OWNER_HEALTH = re.compile(
    r"\b(melhor(?:ou|ando|a|as|ei|zinho)?|melhoras?|recuper\w*|se recuper\w*|já passou|passou (?:a|o) \w+|"
    r"(?:vc|você|voce|tu|o senhor|a senhora|sr|sra)\s+(?:tá|ta|está|esta|anda|amanheceu|passou)\s+(?:bem|melhor|mal)|"
    r"como\s+(?:vc|você|voce|tu|o senhor|a senhora)\s+(?:tá|ta|está|esta|anda|passou|amanheceu|se sente)|"
    r"tá\s+(?:bem|melhor)|está\s+(?:bem|melhor)|ainda\s+(?:doente|gripad\w+|com febre))\b",
    re.IGNORECASE,
)

_SELF_SICK = re.compile(
    r"(?:\b(?:eu\s+)?(?:tô|to|tou|estou|ando|fiquei|estava|tava|estive|tamb[eé]m)\s+(?:\w+\s+){0,2}"
    r"(?:doente|gripad\w+|resfriad\w+|internad\w+|mal|ruim|p[ée]ssim\w+|com\s+(?:febre|gripe|covid|dengue|dor\w*|tosse|virose|sintomas))\b|"
    r"\b(?:peguei|estou\s+com|tô\s+com|to\s+com|tou\s+com)\s+(?:gripe|covid|dengue|virose|febre|dor\w*)\b|"
    r"\b(?:minha|meu)\s+(?:gripe|febre|sa[uú]de|garganta|cabe[cç]a|tosse|dor\w*)\b)",
    re.IGNORECASE,
)

_ADDRESSEE = r"(?:vc|você|voce|tu|o senhor|a senhora|sr|sra|aí|ai|por aí|por ai)"
_HEALTH_WORD = r"(?:melhor\w*|recuper\w*|doente|gripad\w+|febre|sa[uú]de|se cuid\w+|tá bem|ta bem|está bem|como (?:tá|ta|está|esta|anda|passou))"
_BOOMERANG_Q = re.compile(
    rf"(?=.*\b{_ADDRESSEE}\b)(?=.*\b{_HEALTH_WORD}\b)", re.IGNORECASE | re.DOTALL,
)
_SENTENCES = re.compile(r"[^.!?…\n]+[.!?…]*[ \t]*|\n+")


def asks_about_owner_health(text: str) -> bool:
    return bool(_ASKS_OWNER_HEALTH.search(text or ""))


def says_they_are_sick(texts: Iterable[str]) -> bool:
    return any(_SELF_SICK.search(t or "") for t in texts)


def drop_health_boomerang(reply: str) -> str:
    """Remove só as perguntas de saúde dirigidas ao interlocutor. As afirmações sobre o dono ficam intactas."""
    kept = [s for s in _SENTENCES.findall(reply) if not (s.rstrip().endswith("?") and _BOOMERANG_Q.search(s))]
    return "".join(kept).strip()


# --- apelidos do dono: o nome que o contato usa para chamar o DONO nunca é o nome do contato ---------------------------------------------------
# Casos reais: o contato escreve "Oi, pastor Adriane" / "Renatinho e Paz" / "Oi Netinho" e o Gêmeo responde "Entendi, Adriane" / "Faz sentido, Renatinho" /
# "Netinho, deixa eu ser claro"; o filho escreve "pai, você já foi buscar?" e o Gêmeo responde "Pai, acho que...".
_GREETING = r"(?i:oi|ol[aá]|bom\s+dia|boa\s+tarde|boa\s+noite|paz(?:\s+do\s+senhor)?|e\s+a[ií]|fala|salve|opa|hey|hello)"
_TITLE = r"(?i:pastor|pr\.?|irm[ãa]o|irm[ãa]|tio|tia|sr\.?|sra\.?|dona|seu|doutor|dr\.?|dra\.?)"
_NAME = r"[A-ZÁÂÃÀÉÊÍÓÔÕÚÇ][A-Za-zÀ-ÿ]{2,}"
_NOT_NAMES = frozenset(
    "oi ola bom boa paz amem obrigado obrigada sim nao tudo fala opa eita salve hey hello valeu certo show entendi beleza tranquilo "
    "deus senhor jesus gloria aleluia queria preciso pode vamos como quando onde porque que quem qual esse essa isso aquele".split()
)
_AFTER_GREETING = re.compile(rf"{_GREETING}[\s,!.]+(?:{_TITLE}\s+)?({_NAME})")
_MESSAGE_LEAD = re.compile(rf"^\s*({_NAME})\s*(?:,|!|\s+e\s+)")
_KINSHIP = re.compile(r"(?i:(?:^|[,.!?]\s*|\boi\s+|\be\s+a[ií]\s+)(pai|papai|papi|painho)\b|\b(pai|papai|papi|painho)\s*(?=[,!?.]))")


def _plain(text: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def owner_aliases(contact_texts: Iterable[str], contact_name: str = "") -> set[str]:
    """Nomes e termos de parentesco que o CONTATO usa para chamar o dono (nunca o próprio nome do contato)."""
    own = {_plain(t) for t in re.split(r"\W+", contact_name or "") if t}
    found: set[str] = set()
    for text in contact_texts:
        text = text or ""
        for m in _AFTER_GREETING.finditer(text):
            found.add(m.group(1))
        m = _MESSAGE_LEAD.match(text)
        if m:
            found.add(m.group(1))
        for m in _KINSHIP.finditer(text):
            found.add((m.group(1) or m.group(2)).lower())
    return {a for a in found if _plain(a) not in own and _plain(a) not in _NOT_NAMES}


def strip_owner_aliases(reply: str, aliases: Iterable[str]) -> str:
    """Tira da resposta o vocativo que repete um apelido do dono (", Adriane.", "Netinho, ...", "Pai, ..."). O resto da frase fica."""
    reply = reply.strip()
    for alias in sorted(aliases, key=len, reverse=True):
        a = re.escape(alias)
        reply = re.sub(rf"(?i)^{a}\s*[,!:]\s*", "", reply)
        reply = re.sub(rf"(?i),\s*{a}(?=\s*[!?.,])", "", reply)
        reply = re.sub(rf"(?i)\b({_GREETING})\s+{a}\b(?=\s*[,!.?\s])", r"\1", reply)
    reply = re.sub(r"[ \t]{2,}", " ", reply).strip()
    return reply[:1].upper() + reply[1:] if reply else reply


def guard_role_inversion(
    reply: str, inbound_text: str, contact_texts: Iterable[str], *, drop_health_question: bool = True, contact_name: str = "",
) -> str:
    """Resposta final do Gêmeo. Só age quando o interlocutor perguntou pela saúde do dono E nunca disse estar doente
    (nem na mensagem atual nem no histórico). Se sobrar nada, devolve "" e o chamador usa a retenção neutra."""
    reply = strip_author_markers(reply)
    contact_texts = list(contact_texts)
    if drop_health_question:
        aliases = owner_aliases([*contact_texts, inbound_text], contact_name)
        if aliases:
            reply = strip_owner_aliases(reply, aliases)
    if drop_health_question and asks_about_owner_health(inbound_text) and not says_they_are_sick([inbound_text, *contact_texts]):
        return drop_health_boomerang(reply)
    return reply
