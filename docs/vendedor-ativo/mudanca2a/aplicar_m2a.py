"""Mudança 2 (parte A, sem migração de banco): aplica as substituições em copias de handlers.py e messaging.py de producao.

Uso (na pasta com handlers.py.novo e messaging.py.novo, copias dos arquivos do container):  python3 aplicar_m2a.py
Cada trecho antigo precisa existir EXATAMENTE uma vez; senao o script aborta sem gravar nada.
Ao final confere o sha256 dos resultados contra os hashes ja testados.
"""
import hashlib
import pathlib
import sys

EXPECTED_ORIG = {
    "handlers.py.novo": "f7b077199defc5c9",
    "messaging.py.novo": "5b72aae2fcf268a3",
}
EXPECTED_NEW = {"handlers.py.novo": "38561a2e587105e2", "messaging.py.novo": "42397ce3f0bd22d0"}  # os arquivos exatos que passaram nos testes

HANDLERS = []
MESSAGING = []

# ---------------------------------------------------------------------------------------------------- handlers.py
HANDLERS.append(("""logger = get_logger(__name__)


@job_handler("whatsapp.transcribe_audio")""", '''logger = get_logger(__name__)


# ---- Mudança 2 (14/10/2026, autorizada pelo dono): o agente nao age enquanto uma PESSOA atua na conversa; audio suspeito nao vira resposta ----
def _human_pause_minutes() -> float:
    """Minutos de pausa depois que uma pessoa atua. Um arquivo (mudavel com `docker exec ... echo 0 > ...`, sem reiniciar) vale mais que a
    variavel de ambiente HUMAN_PAUSE_MINUTES; sem nenhum dos dois, 30. 0 desliga a pausa."""
    import os

    raw = ""
    try:
        with open(os.environ.get("HUMAN_PAUSE_FILE", "/app/human_pause_minutes.txt"), encoding="utf-8") as handle:
            raw = handle.read().strip()
    except OSError:
        raw = ""
    try:
        return float(raw or os.environ.get("HUMAN_PAUSE_MINUTES", "30"))
    except ValueError:
        return 30.0


def _guard_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _plain_text(text) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", (text or "").lower())
    return " ".join("".join(ch for ch in decomposed if not unicodedata.combining(ch)).split())


# Apresentacoes do proprio robo: nunca contam como "uma pessoa atuou", mesmo se o eco do WhatsApp as gravar como humanas.
_BOT_SELF_INTRO_PREFIXES = ("oi! aqui e o assistente automatico", "aqui e a chroma", "aqui e o twin")
# Frases que o Whisper costuma inventar em audio curto ou com ruido.
_STT_HALLUCINATION_PHRASES = (
    "legendas pela comunidade", "amara.org", "obrigado por assistir", "inscreva-se no canal", "se inscreva no canal", "tchau tchau",
)


def _is_bot_self_intro(text) -> bool:
    return _plain_text(text).startswith(_BOT_SELF_INTRO_PREFIXES)


def _audio_transcript_unreliable(text, min_words: int = 0) -> bool:
    plain = _plain_text(text)
    words = plain.split()
    if not words or len(words) < min_words:
        return True
    if any(phrase in plain for phrase in _STT_HALLUCINATION_PHRASES):
        return True
    return len(words) >= 4 and len(set(words)) / len(words) < 0.4  # repeticao em laco, tipica de alucinacao


async def _human_outbound_after(db, contact_id: int, instance: str, moment) -> bool:
    """True se uma PESSOA escreveu nesta conversa (contato + instancia) depois de `moment`."""
    from sqlalchemy import select

    from models.message import Message

    conditions = [
        Message.contact_id == contact_id,
        Message.direction == MessageDirection.OUTBOUND,
        Message.sent_by_human.is_(True),
        Message.created_at > moment,
    ]
    if instance:
        conditions.append(Message.whatsapp_instance == instance)
    rows = await db.execute(select(Message.content).where(*conditions).order_by(Message.id.desc()).limit(20))
    return any(not _is_bot_self_intro(content) for content in rows.scalars().all())


async def _human_active_recently(db, contact_id: int, instance: str) -> bool:
    minutes = _human_pause_minutes()
    if minutes <= 0:
        return False
    from datetime import datetime, timedelta, timezone

    return await _human_outbound_after(db, contact_id, instance, datetime.now(timezone.utc) - timedelta(minutes=minutes))


async def _human_took_over_before_send(db, payload: dict) -> bool:
    """True se uma pessoa escreveu na conversa depois que o agente comecou a gerar esta resposta."""
    started, contact_id = payload.get("_guard_started_at"), payload.get("_guard_contact_id")
    if not started or contact_id is None:
        return False
    from datetime import datetime

    try:
        moment, contact_id = datetime.fromisoformat(str(started)), int(contact_id)
    except (TypeError, ValueError):
        return False
    return await _human_outbound_after(db, contact_id, str(payload.get("instance") or ""), moment)


def _sent_message_id(response):
    """Id do WhatsApp devolvido pelo gateway no envio ({"key": {"id": ...}}), ou None."""
    key = response.get("key") if isinstance(response, dict) else None
    value = key.get("id") if isinstance(key, dict) else None
    return str(value) if value else None


def _unverified_contact_data(reply: str, allowed_texts: list) -> str | None:
    """Categoria do primeiro e-mail, link ou telefone/documento da resposta que NAO aparece na conversa nem na lista permitida, ou None.
    Caso real: o Twin mandou um e-mail inventado (mensagem 11267). Nunca devolve nem registra o valor achado."""
    import os
    import re

    allowed = "\\n".join([*allowed_texts, os.environ.get("TWIN_ALLOWED_CONTACT_DATA", "dariomneto@hotmail.com")])
    allowed_lower = allowed.lower()
    for match in re.finditer(r"[\\w.+-]+@[\\w-]+(?:\\.[\\w-]+)+", reply):
        if match.group(0).lower() not in allowed_lower:
            return "email"
    for match in re.finditer(r"(?:https?://|www\\.)[^\\s<>\\"]+", reply, re.IGNORECASE):
        if match.group(0).lower().rstrip(".,;:!?)") not in allowed_lower:
            return "link"
    number = re.compile(r"\\+?\\d(?:[\\s().-]*\\d){9,}")
    known = [re.sub(r"\\D", "", m.group(0)) for m in number.finditer(allowed)]
    for match in number.finditer(reply):
        digits = re.sub(r"\\D", "", match.group(0))
        if not any(digits.endswith(k) or k.endswith(digits) for k in known):
            return "telefone_ou_documento"
    return None


@job_handler("whatsapp.transcribe_audio")'''))

HANDLERS.append(("""    if not await _owner_audio_send_guard(db, payload, to, instance):
        return
    provider = get_whatsapp_provider()
    if instance and isinstance(provider, EvolutionProvider):
        await provider.send_text(to, content, instance=instance)
    else:
        await provider.send_text(to, content)
    await persist_outbound_message(db, to, content, is_autopilot_reply=bool(payload.get('is_autopilot_reply')), instance=instance)
""", """    if not await _owner_audio_send_guard(db, payload, to, instance):
        return
    if await _human_took_over_before_send(db, payload):
        await record_log(
            db, source='human_pause', level='info',
            message='Pessoa atuou na conversa durante a geração; resposta automática descartada antes do envio',
            payload={'contact_id': payload.get('_guard_contact_id'), 'instance': instance},
        )
        return
    provider = get_whatsapp_provider()
    if instance and isinstance(provider, EvolutionProvider):
        sent = await provider.send_text(to, content, instance=instance)
    else:
        sent = await provider.send_text(to, content)
    await persist_outbound_message(
        db, to, content, is_autopilot_reply=bool(payload.get('is_autopilot_reply')), instance=instance,
        external_id=_sent_message_id(sent),
    )
"""))

HANDLERS.append(('''    instance = str(payload.get("instance") or "")
    extra_agents = {"b2b-sales": "b2b", "azusa-church": "azusa_intake"}
''', '''    instance = str(payload.get("instance") or "")
    guard_started = _guard_now_iso()
    extra_agents = {"b2b-sales": "b2b", "azusa-church": "azusa_intake"}
'''))

HANDLERS.append(('''        from orchestrator.service import ai_orchestrator
        result = await ai_orchestrator.run(
            db=db, user=owner, message=message.content,
            agent_name=extra_agents[instance], contact_id=None,
            memories=[], history=[],
        )
        if result.reply and result.reply.strip():
            await JobService(db).enqueue(
                "whatsapp.send_text",
                {"to": contact.phone, "content": result.reply, "instance": instance},
            )
        return
''', '''        if await _human_active_recently(db, contact_id, instance):
            logger.info("Extra WhatsApp: pessoa atuando na conversa; agente não age (instância %s)", instance)
            return
        from orchestrator.service import ai_orchestrator
        result = await ai_orchestrator.run(
            db=db, user=owner, message=message.content,
            agent_name=extra_agents[instance], contact_id=None,
            memories=[], history=[],
        )
        if result.reply and result.reply.strip():
            await JobService(db).enqueue(
                "whatsapp.send_text",
                {"to": contact.phone, "content": result.reply, "instance": instance,
                 "_guard_contact_id": contact_id, "_guard_started_at": guard_started},
            )
        return
'''))

HANDLERS.append(('''            return
        from orchestrator.service import ai_orchestrator
        from services.store_sales import confirmation_code, confirm_quote
''', '''            return
        if await _human_active_recently(db, contact_id, instance):
            logger.info("Loja: pessoa atuando na conversa; agente não age (contato %s)", contact_id)
            return
        if getattr(message.media_type, "value", message.media_type) == "audio" and _audio_transcript_unreliable(message.content):
            await record_log(
                db, source="audio_suspeito", level="warning",
                message="Loja: transcrição de áudio pouco confiável; sem resposta automática",
                payload={"contact_id": contact_id, "message_id": message_id, "instance": instance},
            )
            return
        from orchestrator.service import ai_orchestrator
        from services.store_sales import confirmation_code, confirm_quote
'''))

HANDLERS.append(('''    else:
        result = await cognitive_pipeline.process(
            db=db, user=owner, message=message.content, contact_id=contact_id
        )
        reply = result.reply

    if reply.strip():
        await JobService(db).enqueue(
            "whatsapp.send_text",
            {"to": reply_phone, "content": reply, "instance": instance},
        )
''', '''    else:
        if await _human_active_recently(db, contact_id, instance):
            logger.info("Pipeline: pessoa atuando na conversa; agente não age (contato %s)", contact_id)
            return
        result = await cognitive_pipeline.process(
            db=db, user=owner, message=message.content, contact_id=contact_id
        )
        reply = result.reply

    if reply.strip():
        await JobService(db).enqueue(
            "whatsapp.send_text",
            {"to": reply_phone, "content": reply, "instance": instance,
             "_guard_contact_id": contact_id, "_guard_started_at": guard_started},
        )
'''))

HANDLERS.append(('''    if owner is None or message is None or (not contact.phone):
        return
    history = await MessageRepository(db).recent_for_contact(contact_id, limit=15, instance=instance)
''', '''    if owner is None or message is None or (not contact.phone):
        return
    if await _human_active_recently(db, contact_id, instance):
        await record_log(
            db, source='twin_autopilot', level='info',
            message='Pessoa atuando na conversa - Twin em silencio (pausa)',
            payload={'contact_id': contact_id, 'message_id': message_id, 'instance': instance},
        )
        return
    _guard_started = _guard_now_iso()
    history = await MessageRepository(db).recent_for_contact(contact_id, limit=15, instance=instance)
'''))

HANDLERS.append(('''    is_risky, reason = is_high_risk_for_impersonation(message.content, history_texts)
    if not is_risky:
        loop_allowed''', '''    is_risky, reason = is_high_risk_for_impersonation(message.content, history_texts)
    if not is_risky and message.media_type.value == 'audio' and _audio_transcript_unreliable(message.content, min_words=5):
        is_risky, reason = (True, 'áudio com transcrição pouco confiável')
    if not is_risky:
        loop_allowed'''))

HANDLERS.append(('''        except TwinReplyUnavailable:
            is_risky, reason = (True, 'resposta do LLM indisponível')
''', '''        except TwinReplyUnavailable:
            is_risky, reason = (True, 'resposta do LLM indisponível')
        if reply and not is_risky:
            leaked = _unverified_contact_data(reply, [*history_texts, message.content])
            if leaked:
                reply, is_risky, reason = ('', True, f'resposta com dado de contato não verificável ({leaked})')
'''))

HANDLERS.append(("""'_twin_contact_id': contact.id, '_twin_source_message_id': message.id, '_twin_history_digest': _twin_history_digest})
        log_level, log_message = ('info', 'Resposta impersonada enviada')""", """'_twin_contact_id': contact.id, '_twin_source_message_id': message.id, '_twin_history_digest': _twin_history_digest, '_guard_contact_id': contact.id, '_guard_started_at': _guard_started})
        log_level, log_message = ('info', 'Resposta impersonada enviada')"""))

# ---------------------------------------------------------------------------------------------------- messaging.py
MESSAGING.append(('''from sqlalchemy.ext.asyncio import AsyncSession

from jobs.service import JobService''', '''from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from jobs.service import JobService'''))

MESSAGING.append(('''    is_autopilot_reply: bool = False,
    instance: str | None = None,
) -> Message:
    clean_phone = normalize_phone(phone)
    contact = await ContactRepository(db).get_or_create_by_phone(clean_phone)

    settings = get_settings()
    effective_instance = instance or settings.evolution_instance or None

    message = Message(
        contact_id=contact.id,
        direction=MessageDirection.OUTBOUND,
        media_type=media_type,
        content=content,
        is_autopilot_reply=is_autopilot_reply,
        whatsapp_instance=effective_instance,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
''', '''    is_autopilot_reply: bool = False,
    instance: str | None = None,
    external_id: str | None = None,
) -> Message:
    clean_phone = normalize_phone(phone)
    contact = await ContactRepository(db).get_or_create_by_phone(clean_phone)

    settings = get_settings()
    effective_instance = instance or settings.evolution_instance or None

    contact_id = contact.id
    message = await _claim_echo_row(db, contact_id, external_id, is_autopilot_reply)
    if message is None:
        message = Message(
            contact_id=contact_id,
            direction=MessageDirection.OUTBOUND,
            media_type=media_type,
            content=content,
            is_autopilot_reply=is_autopilot_reply,
            whatsapp_instance=effective_instance,
            external_id=external_id,
        )
        db.add(message)
        try:
            await db.commit()
        except IntegrityError:
            # O eco do gateway gravou a mesma mensagem entre a checagem e a gravacao: a linha dele e a verdade; so corrige a autoria.
            await db.rollback()
            contact = await ContactRepository(db).get(contact_id)  # o rollback expira o objeto; recarrega antes de seguir
            message = await _claim_echo_row(db, contact_id, external_id, is_autopilot_reply)
            if message is None:
                raise
        await db.refresh(message)
'''))

MESSAGING.append(('''async def persist_outbound_message(''', '''async def _claim_echo_row(db: AsyncSession, contact_id: int, external_id: str | None, is_autopilot_reply: bool) -> Message | None:
    """Se o eco (fromMe) deste envio chegou ANTES da gravacao e foi guardado como mensagem humana, a linha ja existe com o mesmo
    id do WhatsApp: ela pertence ao app, nao a uma pessoa. Corrige a autoria em vez de duplicar (ou falhar na chave unica).
    So age com id do WhatsApp igual, que e unico por mensagem."""
    if not external_id:
        return None
    existing = (await db.execute(select(Message).where(Message.external_id == external_id))).scalars().first()
    if existing is None or existing.contact_id != contact_id or existing.direction != MessageDirection.OUTBOUND:
        return None
    existing.sent_by_human = False
    existing.is_autopilot_reply = is_autopilot_reply
    await db.commit()
    await db.refresh(existing)
    return existing


async def persist_outbound_message('''))

MESSAGING.append(('''from sqlalchemy.exc import IntegrityError
''', '''from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
'''))


def apply(text: str, pairs: list) -> str:
    for index, (old, new) in enumerate(pairs, 1):
        if text.count(old) != 1:
            sys.exit(f"ABORTAR: trecho {index} nao encontrado exatamente uma vez ({text.count(old)} ocorrencias); nada foi gravado")
        text = text.replace(old, new)
    return text


def main() -> None:
    plans = {"handlers.py.novo": HANDLERS, "messaging.py.novo": MESSAGING}
    results = {}
    for name, pairs in plans.items():
        path = pathlib.Path(name)
        original = path.read_bytes()
        digest = hashlib.sha256(original).hexdigest()[:16]
        if digest != EXPECTED_ORIG[name]:
            sys.exit(f"ABORTAR: {name} tem hash {digest}, esperado {EXPECTED_ORIG[name]} (o container mudou); nada foi gravado")
        results[name] = apply(original.decode("utf-8"), pairs)
    for name, text in results.items():
        new_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        want = EXPECTED_NEW[name]
        if want is not None and new_digest != want:
            sys.exit(f"ABORTAR: resultado de {name} tem hash {new_digest}, esperado {want}; nada foi gravado")
    for name, text in results.items():
        pathlib.Path(name).write_text(text, encoding="utf-8")
        print(name, "OK", hashlib.sha256(text.encode("utf-8")).hexdigest()[:16])


if __name__ == "__main__":
    main()
