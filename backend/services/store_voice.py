"""Resposta por voz do vendedor da loja (Marquescolor): decisão, roteiro, geração, validação e envio pelo Evolution.

Princípios (todos cobertos por testes em tests/test_store_voice.py):
- a voz é COMPLEMENTO do texto escrito: o texto com preços, quantidades e condições já foi entregue pela fila existente
  (`whatsapp.send_text`); o áudio é curto, sem números, e aponta para o texto;
- só a instância da loja envia voz; nunca a pessoal, nem por fallback;
- tudo é conferido de novo DEPOIS da geração e imediatamente antes do envio (cliente respondeu, humano assumiu, pausa,
  opt-out, mensagem velha, limite diário);
- a reserva do envio é gravada e confirmada ANTES do transporte; resultado incerto => `needs_review`, nunca reenvio automático
  e nunca texto de reserva (o texto, aliás, já foi enviado antes);
- falha antes do envio (serviço de voz, formato inválido) => `failed_before_send`: o cliente já tem a resposta por escrito;
- o roteiro identifica o assistente e informa o uso de voz sintética autorizada, e não sugere que o proprietário ouviu ou
  respondeu pessoalmente.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.contact import Contact
from models.message import Message, MessageDirection, MessageMediaType
from models.store_voice import StoreVoiceSend
from providers.whatsapp.base import extract_receipt_id, normalize_phone, provably_not_sent
from providers.whatsapp.factory import get_whatsapp_provider
from repositories.message import MessageRepository
from services import conversation_control, voice_client
from services.audit import record_log
from services.ogg_opus import InvalidVoiceAudio, inspect_ogg_opus
from services.output_safety import output_safe
from utils.config import Settings, get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

KIND_REPLY = "reply"
KIND_FOLLOWUP = "followup"

DISCLOSURE = "Aqui é o assistente virtual da Marquescolor. Estou usando uma voz sintética, autorizada pelo Dário."
POINTER = "Os detalhes, com valores e condições, estão por escrito na mensagem acima. Se precisar, é só responder por aqui."

_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_SPECIFIC = re.compile(r"\d|R\$|reais|%|por cento", re.I)
_CODE = re.compile(r"\b[A-Z0-9]{6,}\b")
_LISTLINE = re.compile(r"^\s*([-•*]|\d+[.)])\s+")
_MARKUP = re.compile(r"[*_`#>~]+")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")


@dataclass(frozen=True)
class VoiceDecision:
    use_voice: bool
    reason: str


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _note(row: StoreVoiceSend, event: str, detail: str | None = None) -> None:
    row.history = [*(row.history or []), {"at": datetime.now(timezone.utc).isoformat(), "event": event, **({"detail": detail} if detail else {})}]


# ---------------------------------------------------------------------------------------------------------------------
# Decisão e roteiro
# ---------------------------------------------------------------------------------------------------------------------
def decide(contact: Contact, source_message: Message | None, settings: Settings | None = None, *, kind: str = KIND_REPLY) -> VoiceDecision:
    s = settings or get_settings()
    if not s.store_voice_enabled:
        return VoiceDecision(False, "voz desligada")
    if not s.store_voice_url or not s.store_voice_token:
        return VoiceDecision(False, "serviço de voz não configurado")
    prefs = contact.preferences or {}
    mode = str(prefs.get("reply_mode", "")).strip().lower()
    if prefs.get("voice_opt_out") or mode in {"text", "texto"}:
        return VoiceDecision(False, "cliente prefere texto")
    if kind == KIND_FOLLOWUP and (prefs.get("store_contact_opt_out") or prefs.get("store_followup_opt_out")):
        return VoiceDecision(False, "cliente pediu para não receber contatos")
    if mode in {"audio", "voz", "áudio"}:
        return VoiceDecision(True, "cliente pediu áudio")
    if s.store_voice_policy == "mirror_audio" and source_message is not None and source_message.media_type == MessageMediaType.AUDIO:
        return VoiceDecision(True, "cliente escreveu por áudio")
    return VoiceDecision(False, "sem preferência por áudio")


def _clean_text(text: str) -> str:
    text = _URL.sub(" ", text)
    text = _EMOJI.sub("", text)
    text = _MARKUP.sub("", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def spoken_summary(reply: str, max_chars: int) -> tuple[str, bool]:
    """(texto falado sem números/códigos/links, `há detalhes só por escrito`). Determinístico: não usa LLM, não inventa nada."""
    cleaned = _clean_text(reply)
    had_url = bool(_URL.search(reply))
    lines = [ln for ln in cleaned.splitlines() if ln.strip()]
    kept: list[str] = []
    details = had_url or len(lines) > 3
    for line in lines:
        if _LISTLINE.match(line) or line.rstrip().endswith(":"):  # item de lista ou cabeçalho que introduz detalhes
            details = True
            break
        sentences = re.split(r"(?<=[.!?])\s+", line.strip())
        stop = False
        for sentence in sentences:
            if _SPECIFIC.search(sentence) or _CODE.search(sentence):
                details = True
                stop = True
                break
            if sum(len(k) + 1 for k in kept) + len(sentence) > max_chars:
                details = True
                stop = True
                break
            kept.append(sentence)
        if stop:
            break
    if len(kept) < sum(len(re.split(r"(?<=[.!?])\s+", ln.strip())) for ln in lines):
        details = True
    return " ".join(kept).strip(), details


def build_script(reply: str, *, disclose: bool, max_chars: int) -> str | None:
    spoken, details = spoken_summary(reply, max_chars)
    parts: list[str] = []
    if disclose:
        parts.append(DISCLOSURE)
    if spoken:
        parts.append(spoken)
    if details or not spoken:
        parts.append(POINTER)
    script = " ".join(parts).strip()
    if not spoken and not details:
        return None  # resposta vazia: nada a falar
    if not output_safe(script).safe:
        return None
    return script


async def _needs_disclosure(db: AsyncSession, contact_id: int, instance: str, days: int) -> bool:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    recent = await db.scalar(
        select(func.count()).select_from(StoreVoiceSend).where(
            StoreVoiceSend.contact_id == contact_id, StoreVoiceSend.instance == instance,
            StoreVoiceSend.status == "sent", StoreVoiceSend.sent_at >= since,
        )
    )
    return not recent


# ---------------------------------------------------------------------------------------------------------------------
# Fila: criação do pedido de voz (chamado depois que o TEXTO foi enviado)
# ---------------------------------------------------------------------------------------------------------------------
async def enqueue_reply_companion(
    db: AsyncSession, *, contact: Contact, source_message: Message | None, reply_text: str, instance: str,
    kind: str = KIND_REPLY, followup_id: int | None = None,
) -> StoreVoiceSend | None:
    from jobs.service import JobService

    s = get_settings()
    if instance != s.evolution_instance or (s.evolution_personal_instance and instance == s.evolution_personal_instance):
        return None  # voz só pela instância da loja
    decision = decide(contact, source_message, s, kind=kind)
    if not decision.use_voice:
        return None
    script = build_script(reply_text, disclose=await _needs_disclosure(db, contact.id, instance, s.store_voice_disclosure_days),
                          max_chars=s.store_voice_max_script_chars)
    if script is None:
        return None
    origin = followup_id if followup_id is not None else (source_message.id if source_message is not None else None)
    if origin is None:
        return None
    key = f"voice:{kind}:{origin}"
    row = StoreVoiceSend(
        dedupe_key=key, kind=kind, contact_id=contact.id, instance=instance,
        source_message_id=source_message.id if source_message is not None else None,
        followup_id=followup_id, status="queued", script_text=script, attempts=0, history=[],
    )
    _note(row, "queued", decision.reason)
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return None  # já existe pedido de voz para esta origem
    # max_attempts=1: se o job morrer no meio, NÃO há reexecução automática (a linha de estado e a reserva decidem).
    await JobService(db).enqueue("store.voice_reply", {"voice_send_id": row.id}, max_attempts=1)
    await db.commit()
    return row


# ---------------------------------------------------------------------------------------------------------------------
# Execução do job
# ---------------------------------------------------------------------------------------------------------------------
async def _gate(db: AsyncSession, row: StoreVoiceSend, contact: Contact | None, source: Message | None, s: Settings) -> str | None:
    """Motivo para NÃO falar agora, ou None. Reconferido antes de gerar e de novo antes de enviar."""
    if not s.store_voice_enabled:
        return "voz desligada"
    if row.instance != s.evolution_instance or (s.evolution_personal_instance and row.instance == s.evolution_personal_instance):
        return "instância não é a da loja"
    if contact is None or not contact.phone:
        return "contato sem telefone"
    prefs = contact.preferences or {}
    if prefs.get("voice_opt_out") or str(prefs.get("reply_mode", "")).strip().lower() in {"text", "texto"}:
        return "cliente prefere texto"
    if row.kind == KIND_FOLLOWUP and (prefs.get("store_contact_opt_out") or prefs.get("store_followup_opt_out")):
        return "cliente pediu para não receber contatos"
    age = (datetime.now(timezone.utc) - _aware(row.created_at)).total_seconds()
    if age > s.store_voice_max_job_age_seconds:
        return "pedido de voz antigo demais"
    if source is not None:
        newer = await db.scalar(
            select(Message.id).where(
                Message.contact_id == row.contact_id, Message.whatsapp_instance == row.instance,
                Message.direction == MessageDirection.INBOUND, Message.id > source.id,
            ).limit(1)
        )
        if newer is not None:
            return "cliente respondeu durante a geração"
        if await MessageRepository(db).has_human_reply_after(source):
            return "atendimento humano assumiu"
    else:  # acompanhamento proativo: não há mensagem do cliente de origem; vale tudo o que aconteceu desde o pedido de voz
        since = _aware(row.created_at) - timedelta(seconds=5)
        newer = await db.scalar(
            select(Message.id).where(
                Message.contact_id == row.contact_id, Message.whatsapp_instance == row.instance,
                Message.direction == MessageDirection.INBOUND, Message.created_at >= since,
            ).limit(1)
        )
        if newer is not None:
            return "cliente respondeu durante a geração"
        human = await db.scalar(
            select(Message.id).where(
                Message.contact_id == row.contact_id, Message.whatsapp_instance == row.instance,
                Message.direction == MessageDirection.OUTBOUND, Message.sent_by_human.is_(True), Message.created_at >= since,
            ).limit(1)
        )
        if human is not None:
            return "atendimento humano assumiu"
    snap = await conversation_control.snapshot(db, row.contact_id, row.instance)
    if snap["paused"]:
        return "conversa pausada"
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    sent_today = await db.scalar(
        select(func.count()).select_from(StoreVoiceSend).where(
            StoreVoiceSend.contact_id == row.contact_id, StoreVoiceSend.status == "sent", StoreVoiceSend.sent_at >= day_ago,
        )
    )
    if (sent_today or 0) >= s.store_voice_max_per_contact_per_day:
        return "limite diário de áudios atingido"
    return None


async def _finish(db: AsyncSession, row: StoreVoiceSend, status: str, reason: str | None, *, event: str | None = None) -> None:
    row.status, row.reason = status, reason
    _note(row, event or status, reason)
    await db.commit()


async def deliver(db: AsyncSession, payload: dict) -> None:
    s = get_settings()
    row = await db.get(StoreVoiceSend, int(payload["voice_send_id"]))
    if row is None:
        return
    if row.status == "generating":  # execução anterior caiu durante a geração: nada foi enviado
        await _finish(db, row, "failed_before_send", "execução interrompida durante a geração")
        return
    if row.status != "queued":
        return  # já tratado (cancelado, enviado, em envio ou para revisão): nunca reprocessa

    contact = await db.get(Contact, row.contact_id)
    source = await db.get(Message, row.source_message_id) if row.source_message_id else None
    reason = await _gate(db, row, contact, source, s)
    if reason:
        await _finish(db, row, "cancelled", reason)
        return

    row.status, row.attempts = "generating", row.attempts + 1
    _note(row, "generating")
    await db.commit()
    try:
        audio = await voice_client.synthesize(row.script_text, f"voice-{row.id}")
    except voice_client.VoiceError as exc:
        await _finish(db, row, "failed_before_send", f"serviço de voz: {exc.code}")
        return
    try:
        info = inspect_ogg_opus(audio.data, max_bytes=s.store_voice_max_audio_bytes, max_seconds=s.store_voice_max_audio_seconds)
    except InvalidVoiceAudio as exc:
        await _finish(db, row, "failed_before_send", f"áudio inválido: {exc}")
        return
    row.audio_sha256, row.audio_seconds, row.audio_bytes = audio.sha256, info.duration_seconds, info.size_bytes
    row.engine, row.model_revision, row.reference_sha256 = audio.engine, audio.model_revision, audio.reference_sha256
    await db.commit()

    # A geração pode demorar: o mundo mudou? Reconfere TUDO imediatamente antes de reservar o envio.
    contact = await db.get(Contact, row.contact_id, populate_existing=True)
    source = await db.get(Message, row.source_message_id, populate_existing=True) if row.source_message_id else None
    fresh = await db.get(StoreVoiceSend, row.id, populate_existing=True)
    if fresh is None:
        return
    row = fresh
    reason = await _gate(db, row, contact, source, s)
    if reason or contact is None or not contact.phone:
        await _finish(db, row, "cancelled", f"{reason or 'contato sem telefone'} (após gerar)")
        return

    intent = f"voice-send:{row.id}"
    decision = await conversation_control.reserve_plain_send(db, row.contact_id, row.instance, intent)
    if decision != "reserved":
        await db.rollback()
        fresh = await db.get(StoreVoiceSend, row.id, populate_existing=True)
        if fresh is not None:
            await _finish(db, fresh, "cancelled" if decision == "paused" else "needs_review", f"reserva de envio: {decision}")
        return
    row.status = "sending"
    _note(row, "sending")
    await db.commit()  # reserva + estado confirmados ANTES do transporte

    provider = get_whatsapp_provider()
    if getattr(provider, "name", "") != "evolution" or not hasattr(provider, "send_voice"):
        await conversation_control.release_unsent_plain_send(db, intent)
        await _finish(db, row, "failed_before_send", "provedor atual não envia mensagem de voz")
        return
    try:
        result = await provider.send_voice(normalize_phone(contact.phone), base64.b64encode(audio.data).decode("ascii"), instance=row.instance)
    except Exception as exc:  # noqa: BLE001
        if provably_not_sent(exc):
            await conversation_control.release_unsent_plain_send(db, intent)
            await _finish(db, row, "failed_before_send", "transporte provadamente não enviou")
        else:
            await _finish(db, row, "needs_review", f"resultado do envio incerto ({type(exc).__name__}); não reenviado")
            await record_log(db, source="store_voice", level="warning", message="Envio de voz com resultado incerto: revisar",
                             payload={"voice_send_id": row.id, "contact_id": row.contact_id, "instance": row.instance})
            await db.commit()
        return

    receipt = extract_receipt_id(result)
    await conversation_control.finish_send(db, intent, receipt)
    db.add(Message(
        contact_id=row.contact_id, direction=MessageDirection.OUTBOUND, media_type=MessageMediaType.AUDIO,
        content=f"[áudio de voz sintética autorizada] {row.script_text}", external_id=receipt,
        is_autopilot_reply=True, whatsapp_instance=row.instance,
    ))
    row.receipt_id, row.sent_at = receipt, datetime.now(timezone.utc)
    if receipt:
        await _finish(db, row, "sent", None)
    else:
        await _finish(db, row, "needs_review", "aceito pelo provedor sem recibo; conferir a entrega", event="accepted_without_receipt")


async def reconcile_stuck(db: AsyncSession, *, older_than_seconds: int = 900) -> dict[str, int]:
    """Linhas que um processo morto deixou no meio. Geração interrompida: nada foi enviado. Envio interrompido: INCERTO."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
    counts = {"generating": 0, "sending": 0}
    rows = (await db.scalars(select(StoreVoiceSend).where(StoreVoiceSend.status.in_(("generating", "sending")), StoreVoiceSend.updated_at <= cutoff))).all()
    for row in rows:
        if row.status == "generating":
            await _finish(db, row, "failed_before_send", "interrompido durante a geração (reconciliação)")
            counts["generating"] += 1
        else:
            await _finish(db, row, "needs_review", "interrompido durante o envio: resultado incerto (reconciliação); não reenviado")
            counts["sending"] += 1
    return counts
