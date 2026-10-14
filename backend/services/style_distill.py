"""Aprendizado do estilo do dono (`darius.distill_style`, "Fase 2" prevista em orchestrator/twin_risk_gate.py).

O que faz: percorre as mensagens que uma PESSOA escreveu (nao o robo), pareia cada uma com a mensagem do cliente que ela respondeu e
guarda o par "Pergunta/Resposta" na memoria vetorial, numa origem propria por instancia (`style_example:<instancia>`). Na hora de
responder, o Twin busca os pares mais parecidos com a mensagem recebida e os usa como EXEMPLOS DE CADENCIA.

O que nao faz: nao treina nem altera o modelo; nao escreve fatos; nao envia nada. Os exemplos so entram no prompt como estilo.

Por que filtra tanto: um corpus de estilo contaminado ensina o erro. Os filtros abaixo existem por causa de casos reais da producao:
- a mensagem de espera do proprio robo foi gravada como "humana" (id 11394) -> textos automaticos conhecidos ficam fora;
- a transcricao inventou texto em audio curto ("Devemos outro bem.", id 11393) -> audio so entra com texto longo o bastante;
- e-mail, telefone, valor e link de terceiros nao podem vazar de um exemplo para outra conversa;
- assuntos de risco (crise, negocio, financeiro) seguem a MESMA classificacao do portao de risco (`classify_text`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from memory.manager import memory_manager
from models.message import Message, MessageDirection, MessageMediaType
from orchestrator.twin_risk_gate import classify_text, normalize_text
from services.audit import record_log
from utils.config import get_settings

MAX_REPLY_CHARS = 400  # resposta de WhatsApp; texto maior nao e estilo de conversa
MAX_QUESTION_CHARS = 600
MIN_REPLY_CHARS = 2
QUESTION_MAX_AGE = timedelta(hours=6)

# Apresentacoes do proprio robo: nunca sao o jeito de escrever de uma pessoa.
_AUTOMATIC_PREFIXES = tuple(
    normalize_text(text)
    for text in (
        "Oi! Aqui é o assistente automático",
        "Aqui é a Chroma",
        "Aqui é o Twin",
    )
)

# Frases que o Whisper costuma inventar em audio curto ou com ruido.
_STT_HALLUCINATIONS = tuple(
    normalize_text(text)
    for text in (
        "legendas pela comunidade",
        "amara.org",
        "obrigado por assistir",
        "inscreva-se no canal",
        "se inscreva no canal",
        "tchau tchau",
    )
)

_EMAIL = re.compile(r"\S+@\S+\.\S+")
_LINK = re.compile(r"https?://|www\.", re.IGNORECASE)
_LONG_NUMBER = re.compile(r"(?:\d[\s.\-()]*){8,}")  # telefone, CPF/CNPJ, conta, chave PIX numerica
_MONEY = re.compile(r"r\$\s*\d|\d+[\d.,]*\s*(?:reais|mil\b)", re.IGNORECASE)


@dataclass
class DistillStats:
    scanned: int = 0
    indexed: int = 0
    last_id: int = 0
    rejected: dict[str, int] = field(default_factory=dict)

    def reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1


def _split_setting(value: str, separator: str) -> list[str]:
    return [part.strip() for part in value.split(separator) if part.strip()]


def style_instances() -> list[str]:
    """Instancias das quais se aprende: as configuradas ou, vazio, a pessoal."""
    settings = get_settings()
    configured = _split_setting(settings.style_instances, ",")
    if configured:
        return configured
    return [settings.evolution_personal_instance] if settings.evolution_personal_instance else []


def excluded_texts() -> frozenset[str]:
    """Textos automaticos exatos (ex.: saudacao e ausencia do WhatsApp Business), normalizados."""
    return frozenset(normalize_text(text) for text in _split_setting(get_settings().style_excluded_texts, "|"))


def _looks_like_stt_noise(text: str, min_words: int) -> bool:
    normalized = normalize_text(text)
    words = normalized.split()
    if len(words) < min_words:
        return True
    if any(phrase in normalized for phrase in _STT_HALLUCINATIONS):
        return True
    return len(set(words)) / len(words) < 0.4  # repeticao em laco, tipica de alucinacao


def check_text(
    text: str,
    *,
    from_audio: bool,
    max_chars: int,
    min_chars: int,
    excluded: frozenset[str],
    min_audio_words: int,
    include_financial: bool,
) -> str | None:
    """Motivo da recusa ou None se o texto pode virar exemplo."""
    text = (text or "").strip()
    if not text:
        return "vazio"
    normalized = normalize_text(text)
    if normalized in excluded or normalized.startswith(_AUTOMATIC_PREFIXES):
        return "texto_automatico"
    if len(text) < min_chars:
        return "curto"
    if len(text) > max_chars:
        return "longo"
    if from_audio and _looks_like_stt_noise(text, min_audio_words):
        return "audio_suspeito"
    if _EMAIL.search(text) or _LINK.search(text) or _LONG_NUMBER.search(text) or _MONEY.search(text):
        return "dado_pessoal_ou_valor"
    risk = classify_text(text)
    if risk is not None and not (include_financial and risk[0] == "financeiro"):
        return "assunto_de_risco"
    return None


def build_example(question: str, reply: str) -> str:
    return f"Pergunta: {question.strip()[:MAX_QUESTION_CHARS]}\nResposta: {reply.strip()}"


def _is_audio(message: Message) -> bool:
    return message.media_type == MessageMediaType.AUDIO


async def _previous_inbound(db: AsyncSession, message: Message) -> Message | None:
    """A mensagem imediatamente anterior da conversa, se for do cliente e recente.

    So a PRIMEIRA resposta do dono depois da pergunta forma um par: as seguintes ("Pode deixar", "Abraço")
    respondem ao proprio dono, nao ao cliente.
    """
    statement = (
        select(Message)
        .where(
            Message.contact_id == message.contact_id,
            Message.whatsapp_instance == message.whatsapp_instance,
            Message.id < message.id,
        )
        .order_by(Message.id.desc())
        .limit(1)
    )
    previous = (await db.execute(statement)).scalars().first()
    if previous is None or previous.direction != MessageDirection.INBOUND:
        return None
    if message.created_at - previous.created_at > QUESTION_MAX_AGE:
        return None
    return previous


async def distill_batch(db: AsyncSession, *, after_id: int = 0) -> DistillStats:
    """Processa um lote de mensagens do dono com id > `after_id`, em ordem crescente.

    Idempotente: cada exemplo tem chave externa `style:<id da mensagem>`; repetir o lote substitui, nao duplica.
    """
    settings = get_settings()
    stats = DistillStats(last_id=after_id)
    instances = style_instances()
    if not instances:
        return stats
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.style_distill_lookback_days)
    statement = (
        select(Message)
        .where(
            Message.id > after_id,
            Message.direction == MessageDirection.OUTBOUND,
            Message.sent_by_human.is_(True),
            or_(Message.is_autopilot_reply.is_(False), Message.is_autopilot_reply.is_(None)),
            Message.whatsapp_instance.in_(instances),
            Message.media_type.in_([MessageMediaType.TEXT, MessageMediaType.AUDIO]),
            Message.created_at >= cutoff,
        )
        .order_by(Message.id)
        .limit(settings.style_distill_batch_size)
    )
    excluded = excluded_texts()

    def problem(text: str, *, audio: bool, max_chars: int) -> str | None:
        return check_text(
            text,
            from_audio=audio,
            max_chars=max_chars,
            min_chars=MIN_REPLY_CHARS,
            excluded=excluded,
            min_audio_words=settings.style_audio_min_words,
            include_financial=settings.style_include_financial,
        )

    for message in (await db.execute(statement)).scalars().all():
        stats.scanned += 1
        stats.last_id = message.id
        reply_problem = problem(message.content, audio=_is_audio(message), max_chars=MAX_REPLY_CHARS)
        if reply_problem:
            stats.reject(f"resposta_{reply_problem}")
            continue
        question = await _previous_inbound(db, message)
        if question is None:
            stats.reject("sem_pergunta_anterior")
            continue
        question_problem = problem(question.content, audio=_is_audio(question), max_chars=MAX_QUESTION_CHARS)
        if question_problem:
            stats.reject(f"pergunta_{question_problem}")
            continue
        await memory_manager.index_style_example(
            db, str(message.whatsapp_instance), message.id, build_example(question.content, message.content)
        )
        stats.indexed += 1
    return stats


async def record_distill_log(db: AsyncSession, stats: DistillStats) -> None:
    await record_log(
        db,
        source="style.distill",
        message="Aprendizado de estilo: lote processado",
        payload={
            "scanned": stats.scanned,
            "indexed": stats.indexed,
            "last_id": stats.last_id,
            "rejected": stats.rejected,
        },
    )


async def retrieve_style_examples(query: str, instance: str) -> list[str]:
    """Pares Pergunta/Resposta mais parecidos com `query`, da instancia indicada."""
    settings = get_settings()
    if not query.strip() or not instance:
        return []
    results = await memory_manager.style_search(query, instance, limit=settings.style_examples_limit)
    return [
        item["content"]
        for item in results
        if item.get("content") and float(item.get("score") or 0.0) >= settings.style_min_score
    ]
