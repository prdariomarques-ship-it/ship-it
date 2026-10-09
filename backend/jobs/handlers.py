"""Built-in job handlers."""

from sqlalchemy.ext.asyncio import AsyncSession

from database.session import async_session_factory
from events.bus import Event, event_bus
from jobs.registry import job_handler
from jobs.service import JobService
from memory.contact_memory import contact_memory_service
from models.message import MessageDirection
from providers.mail.base import MailProviderError
from providers.mail.factory import get_mail_provider
from providers.whatsapp.factory import get_whatsapp_provider
from repositories.contact import ContactRepository
from repositories.email_account import EmailAccountRepository
from repositories.message import MessageRepository
from repositories.user import UserRepository
from services.audit import record_log
from services.messaging import persist_outbound_message
from services.rate_limit import rate_limiter
from services.token_crypto import decrypt_token
from utils.logging import get_logger
from workflows.service import workflow_service

logger = get_logger(__name__)


@job_handler("whatsapp.transcribe_audio")
async def transcribe_whatsapp_audio(db: AsyncSession, payload: dict) -> None:
    from providers.stt.base import STTProviderError
    from providers.whatsapp.base import InboundMessage
    from webhooks.router import _transcribe_audio, dispatch_inbound

    message = await MessageRepository(db).get(int(payload["message_id"]))
    if message is None or message.direction != MessageDirection.INBOUND:
        return
    from repositories.job import JobRepository

    if message.media_type.value != "audio":
        return
    # Resume a crash between transcript persistence and reply enqueueing,
    # while never enqueueing twice if that reply was already committed.
    if await JobRepository(db).has_inbound_reply(message.id):
        return
    contact = await ContactRepository(db).get(message.contact_id)
    if contact is None:
        return
    inbound = InboundMessage(
        phone=contact.phone, text="", external_id=message.external_id or "",
        media_type="audio", timestamp=message.provider_timestamp,
        instance=message.whatsapp_instance,
        media_key=payload.get("media_key"),
    )
    provider = get_whatsapp_provider()
    inbound.text = message.content.strip() or await _transcribe_audio(db, provider, inbound)
    if not inbound.text.strip():
        # Durable retries cover temporary download/service failures. Never
        # send fabricated speech to the conversational agent.
        raise STTProviderError("Audio sem transcricao; verificar midia ou servico de voz")
    message.content = inbound.text
    # The owner can reply while the audio is being decoded. Preserve that
    # intervention instead of re-arming the Twin after the human answered.
    if await MessageRepository(db).has_human_reply_after(message):
        await db.commit()
        return
    await dispatch_inbound(db, provider, inbound, contact, message, "audio")
    await db.commit()


@job_handler("store.aftercare_followup")
async def store_aftercare_followup(db: AsyncSession, payload: dict) -> None:
    from services.store_aftercare import send_followup

    await send_followup(db, int(payload["delivery_id"]))

APOLOGY_MESSAGE = "Desculpe, tive um problema para responder agora. O Dario vai revisar sua mensagem em breve."


@job_handler("contact.summarize")
async def summarize_contact(db: AsyncSession, payload: dict) -> None:
    """Refresh a contact's automatic profile summary."""
    await contact_memory_service.summarize_contact(db, int(payload["contact_id"]))


@job_handler("memory.embed")
async def embed_interaction(db: AsyncSession, payload: dict) -> None:
    """Embed an interaction into the vector memory (off the message hot path)."""
    from memory.service import memory_service

    await memory_service.store(
        db,
        content=str(payload["content"]),
        source=str(payload.get("source", "whatsapp")),
        contact_id=payload.get("contact_id"),
    )


@job_handler("catalog.index_product")
async def index_product(db: AsyncSession, payload: dict) -> None:
    """(Re)embed a product for semantic search, or drop its vector if it
    was deactivated/removed since the job was queued -- off the CSV-import
    hot path (see services/store_catalog.py::import_catalog)."""
    from memory.manager import memory_manager
    from repositories.product import ProductRepository

    sku = str(payload["sku"])
    product = await ProductRepository(db).get_by_sku(sku)
    if product is None or not product.active:
        await memory_manager.deindex_product(db, sku)
        return
    content = f"{product.name} — categoria: {product.category or 'geral'} — unidade: {product.unit}"
    await memory_manager.index_product(db, sku, content)


@job_handler('whatsapp.send_text')
async def send_whatsapp_text(db: AsyncSession, payload: dict) -> None:
    """Send a WhatsApp text through the configured provider (with queue retry),
    then persist it and feed the contact memory — same bookkeeping as the
    dashboard-triggered send, whether this was queued by the automatic reply
    or by an agent's send_whatsapp_message tool call.

    An optional `instance` in the payload routes the reply back out through
    that same Evolution gateway instance (see evolution_personal_instance) --
    so a personal-number conversation is answered from the personal number,
    not the store's. Only EvolutionProvider understands this; every other
    provider (and a call with no `instance`) behaves exactly as before.

    Two independent, deliberately separate transactional fences apply here
    (services/conversation_control.py, reused verbatim from the V2
    candidate -- see DELIVERY_NOTES.md), so a failure or uncertain outcome
    of one can never trigger a blind repeat of the other:

      - an autopilot reply TO A CLIENT (`is_autopilot_reply` + the twin's
        `_twin_*` fields) goes through `claim_send`/`finish_send`, keyed
        by contact+instance+the source message -- this is the "revalidate
        the human-pause control immediately before transport" fence. A
        pause that happened after generation started (even mid-generation)
        makes `claim_send` fail here, atomically, regardless of how long
        generation took.
      - an owner alert (`_twin_alert_dedup_key`, set by
        orchestrator/incident_dedup.py's decide_owner_alert) goes through
        `claim_alert`/`finish_alert` instead, keyed by the SAME
        contact+instance but a content-derived dedup key -- never the
        send fence above. The owner being alerted about a paused
        conversation is exactly when the alert must still go out, so it
        is never blocked by that conversation's own pause state.

    Neither fence applies to any other call of this job (a plain
    dashboard-triggered send, mail-adjacent notifications, etc.) -- those
    behave exactly as before."""
    from providers.whatsapp.evolution.provider import EvolutionProvider
    from services import conversation_control
    from services.output_safety import output_safe
    to = str(payload['to'])
    content = str(payload['content'])
    instance = payload.get('instance') or None
    if not await _owner_audio_send_guard(db, payload, to, instance):
        return
    # Last point before transport -- see services/output_safety.py's module
    # docstring for why this must live here (the one chokepoint every
    # caller converges on) and not only in the generating callers above.
    # Covers retries and re-queued jobs for free: this runs every time the
    # job executes, including a retry of a payload generated before this
    # check existed.
    safety = output_safe(content)
    if not safety.safe:
        await record_log(
            db, source="output_safety", level="error",
            message="Envio bloqueado: conteúdo não seguro para transporte",
            payload={"to_last4": to[-4:], "reason": safety.reason, "instance": instance},
        )
        return
    send_intent_id = None
    alert_contact_id = payload.get('_twin_alert_contact_id')
    alert_dedup_key = payload.get('_twin_alert_dedup_key')
    if alert_contact_id is not None and alert_dedup_key:
        claimed = await conversation_control.claim_alert(db, int(alert_contact_id), instance or '', alert_dedup_key)
        if claimed != 'claimed':
            await record_log(
                db, source='twin_owner_alert', level='info',
                message=f'Envio de alerta ao proprietário não realizado (status: {claimed})',
                payload={'contact_id': alert_contact_id, 'instance': instance, 'dedup_key': alert_dedup_key},
            )
            await db.commit()
            return
    elif payload.get('is_autopilot_reply') and payload.get('_twin_contact_id') is not None and payload.get('_twin_revision') is not None:
        contact_id = int(payload['_twin_contact_id'])
        source_message_id = payload.get('_twin_source_message_id')
        send_intent_id = f"twin-send:{contact_id}:{instance}:{source_message_id}"
        claimed = await conversation_control.claim_send(db, contact_id, instance or '', int(payload['_twin_revision']), send_intent_id)
        if claimed != 'claimed':
            await record_log(
                db, source='twin_autopilot', level='info',
                message=f'Envio automático suprimido (status: {claimed}) -- controle humano revalidado antes do transporte',
                payload={'contact_id': contact_id, 'instance': instance, 'intent_id': send_intent_id},
            )
            await db.commit()
            return
    provider = get_whatsapp_provider()
    if instance and isinstance(provider, EvolutionProvider):
        await provider.send_text(to, content, instance=instance)
    else:
        await provider.send_text(to, content)
    await persist_outbound_message(db, to, content, is_autopilot_reply=bool(payload.get('is_autopilot_reply')), instance=instance)
    # No receipt id is available from this provider call in the sources
    # this delivery was built from -- an uncertain outcome is recorded
    # honestly (`receipt_id=None` keeps the intent at 'needs_review') and
    # is never promoted to "sent" without one. See DELIVERY_NOTES.md.
    if send_intent_id is not None:
        await conversation_control.finish_send(db, send_intent_id, None)
    if alert_contact_id is not None and alert_dedup_key:
        await conversation_control.finish_alert(db, int(alert_contact_id), instance or '', alert_dedup_key, None)


@job_handler("mail.send_reply")
async def send_mail_reply(db: AsyncSession, payload: dict) -> None:
    """Reply within an existing Gmail thread (queue retry covers a
    transient Gmail outage, same reasoning as whatsapp.send_text). Access
    token isn't cached anywhere -- refreshed fresh from the stored
    (encrypted) refresh token every time, same as agents/tools/mail.py's
    own _get_access_token."""
    user_id = int(payload["user_id"])
    thread_id = str(payload["thread_id"])

    provider = get_mail_provider()
    account = await EmailAccountRepository(db).get_by_user(user_id, provider.name)
    if account is None:
        logger.error("mail.send_reply: no email account for user %s", user_id)
        return
    refresh_token = decrypt_token(account.encrypted_refresh_token)
    tokens = await provider.refresh_access_token(refresh_token)

    try:
        message_id = await provider.send_reply(
            tokens.access_token,
            thread_id=thread_id,
            to=list(payload["to"]),
            subject=str(payload["subject"]),
            body=str(payload["body"]),
            in_reply_to_message_id=payload.get("in_reply_to_message_id"),
        )
    except MailProviderError:
        raise  # let the job queue's own retry/backoff handle a transient failure

    await record_log(
        db,
        source=f"mail:reply:{user_id}",
        message=f"Email reply sent in thread {thread_id}",
        level="info",
        payload={"thread_id": thread_id, "message_id": message_id},
    )


@job_handler("workflow.trigger")
async def trigger_workflow(db: AsyncSession, payload: dict) -> None:
    """Fire an n8n workflow; queue retries cover transient n8n outages."""
    await workflow_service.trigger(
        str(payload["workflow"]), dict(payload.get("data", {}))
    )


@job_handler("whatsapp.process_inbound")
async def process_inbound_whatsapp_message(db: AsyncSession, payload: dict) -> None:
    """The automatic end-to-end reply: the Cognitive Pipeline (Fase 4.2)
    classifies intent/priority, plans, picks the agent(s), runs them (memory
    + tools), validates the result, and updates memory — then the reply is
    queued back through the existing whatsapp.send_text job, so sending
    inherits the same retry as everything else. This is the piece that makes
    the WhatsApp flow work without n8n.
    """
    from orchestrator.pipeline import cognitive_pipeline

    contact_id = int(payload["contact_id"])
    message_id = int(payload["message_id"])

    contact = await ContactRepository(db).get(contact_id)
    message = await MessageRepository(db).get(message_id)
    owner = await UserRepository(db).get_first_admin()
    if (
        contact is None
        or message is None
        or owner is None
        or not contact.phone
        or message.contact_id != contact_id
        or message.direction != MessageDirection.INBOUND
    ):
        logger.warning(
            "Skipping auto-reply: contact=%s message=%s owner=%s",
            contact_id,
            message_id,
            owner is not None,
        )
        return

    from utils.config import get_settings

    settings = get_settings()
    instance = str(payload.get("instance") or "")
    extra_agents = {"b2b-sales": "b2b", "azusa-church": "azusa_intake"}
    if instance in extra_agents:
        if not settings.auto_reply_enabled:
            return
        if getattr(message, "whatsapp_instance", None) != instance:
            logger.warning("Extra WhatsApp: instância da mensagem divergente")
            return
        if getattr(message.media_type, "value", message.media_type) != "text":
            logger.info("Extra WhatsApp: somente texto nesta etapa")
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
                {"to": contact.phone, "content": result.reply, "instance": instance},
            )
        return
    personal_instance = settings.evolution_personal_instance
    # Safety fallback mirroring webhooks/router.py's own instance gate: even if
    # store_whatsapp_enabled is globally True, a message that arrived on the
    # dedicated personal instance must never be handed to store_agent -- it
    # always goes through cognitive_pipeline (and, when enabled, the Digital
    # Twin -- see twin_autopilot_check / router.py's use_twin gate).
    is_personal_instance = bool(personal_instance) and instance == personal_instance

    reply_phone = contact.phone
    if settings.store_whatsapp_enabled and not is_personal_instance:
        from services.store_aftercare import is_stop_request, stop_followups

        if is_stop_request(message.content):
            await stop_followups(db, contact)
            await JobService(db).enqueue("whatsapp.send_text", {
                "to": reply_phone,
                "content": "Pronto: seus acompanhamentos automáticos de pós-venda foram cancelados. Você pode continuar falando com a loja por aqui.",
                "instance": instance,
            })
            return
        from orchestrator.service import ai_orchestrator
        from services.store_sales import confirmation_code, confirm_quote

        # Only the original persisted customer's input may confirm a quote.
        # An LLM-generated plan objective or tool argument is never approval.
        code = confirmation_code(message.content)
        if code:
            try:
                order = await confirm_quote(db, contact_id, code)
                total = order["order"]["total"].replace(".", ",")
                reply = (
                    f"Pedido {code} registrado. Total dos produtos: R$ {total}. "
                    "Pagamento, frete e prazo de entrega serão combinados com a equipe."
                )
            except ValueError as exc:
                reply = str(exc)
        else:
            result = await ai_orchestrator.run(
                db=db,
                user=owner,
                message=message.content,
                contact_id=contact_id,
                agent_name="store",
            )
            reply = result.reply
    else:
        result = await cognitive_pipeline.process(
            db=db, user=owner, message=message.content, contact_id=contact_id
        )
        reply = result.reply

    if reply.strip():
        await JobService(db).enqueue(
            "whatsapp.send_text",
            {"to": reply_phone, "content": reply, "instance": instance},
        )


TWIN_HOLDING_MESSAGE = (
    "Oi! Aqui é o assistente automático do Dário. Este assunto precisa "
    "da resposta pessoal dele."
)


@job_handler('whatsapp.twin_autopilot_check')
async def twin_autopilot_check(db: AsyncSession, payload: dict) -> None:
    """Digital twin: runs `whatsapp_twin_idle_timeout_seconds` after an inbound
    text. If the owner still hasn't answered, either the twin replies in his
    voice or -- for sensitive topics -- a neutral holding message goes out and
    the owner is alerted. Never sends anything for a conversation that was
    already answered, or superseded by a newer message (that one has its own
    check job).

    Human-pause: before anything else (including before spending an LLM
    call), this checks services/conversation_control.snapshot for this
    (contact, instance). A conversation already paused (owner or an
    attendant took over) returns immediately -- no generation, no send.
    The `revision` read here is then carried through to the enqueued
    send-job payload as `_twin_revision`, so send_whatsapp_text's
    `claim_send` re-checks it atomically right before transport: a pause
    that happens AFTER this point (including mid-generation) still blocks
    the send, because the revision captured here will no longer match by
    the time claim_send runs."""
    from agents.darius_twin import TwinReplyUnavailable, generate_darius_reply
    from orchestrator.incident_dedup import decide_owner_alert
    from orchestrator.twin_risk_gate import HistoryEntry, MessageAuthor, RiskEvidence, is_high_risk_for_impersonation
    from providers.llm.base import ChatMessage
    from services import conversation_control
    from utils.config import get_settings
    settings = get_settings()
    if not settings.whatsapp_twin_mode_enabled:
        return
    contact_id = int(payload['contact_id'])
    message_id = int(payload['message_id'])
    instance = str(payload.get('instance') or '')
    control_state = await conversation_control.snapshot(db, contact_id, instance)
    if control_state['paused']:
        await record_log(
            db, source='twin_autopilot', level='info',
            message='Conversa pausada por controle humano -- nenhuma geração ou envio automático',
            payload={'contact_id': contact_id, 'instance': instance},
        )
        return
    revision = control_state['revision']
    contact = await ContactRepository(db).get(contact_id)
    if contact is None or contact.awaiting_reply_since is None:
        return
    latest_inbound = await MessageRepository(db).get_latest_inbound(contact_id, instance=instance)
    if latest_inbound is None or latest_inbound.id != message_id:
        return
    owner = await UserRepository(db).get_first_admin()
    message = await MessageRepository(db).get(message_id)
    if owner is None or message is None or (not contact.phone):
        return
    history = await MessageRepository(db).recent_for_contact(contact_id, limit=15, instance=instance)
    await _owner_audio_refresh_history(db, history, instance)
    if not await _owner_audio_generation_guard(db, contact, message, instance, history):
        return
    _twin_history_digest = _owner_audio_history_digest(history)
    _twin_pending_snapshot = contact.awaiting_reply_since

    def _author_of(m) -> 'MessageAuthor':
        # Conservative by design: anything that is not clearly inbound
        # (client), a recorded human send (owner) or our own autopilot
        # reply (bot) is UNKNOWN -- never silently defaulted to CLIENT,
        # per the review's "origem incerta deve ser registrada como
        # incerta".
        if m.direction == MessageDirection.INBOUND:
            return MessageAuthor.CLIENT
        if getattr(m, 'is_autopilot_reply', False):
            return MessageAuthor.BOT
        if getattr(m, 'sent_by_human', False):
            return MessageAuthor.OWNER
        return MessageAuthor.UNKNOWN

    history_entries = [
        HistoryEntry(m.id, _author_of(m), m.provider_timestamp or m.created_at, _owner_audio_history_content(m))
        for m in history
        if _owner_audio_history_content(m)
    ]
    evidence = is_high_risk_for_impersonation(message.id, message.content, history_entries)
    is_risky = evidence is not None
    reason = evidence.reason() if evidence else ''
    if not is_risky:
        loop_allowed = await rate_limiter.is_allowed(f'twin-loop:{instance}:{contact_id}', limit=settings.whatsapp_twin_loop_guard_max_replies, window_seconds=settings.whatsapp_twin_loop_guard_window_seconds)
        if not loop_allowed:
            is_risky = True
            reason = f'loop: {settings.whatsapp_twin_loop_guard_max_replies}+ respostas automáticas em {settings.whatsapp_twin_loop_guard_window_seconds // 60}min -- provável automação do outro lado'
            # Synthetic evidence so the dedup fingerprint below is stable
            # for this category too (no RiskEvidence from the content gate
            # in the loop-guard branch).
            evidence = RiskEvidence(
                category='loop', snippet='loop_guard', source_message_id=message.id,
                source_author=MessageAuthor.UNKNOWN, source_created_at=None, in_current_message=True,
            )
    reply = ''
    if not is_risky:
        chat_history = [ChatMessage(role='user' if m.direction == MessageDirection.INBOUND else 'assistant', content=_owner_audio_history_content(m)) for m in history if _owner_audio_history_content(m) and m.id != message_id]
        try:
            reply = await generate_darius_reply(chat_history, message.content, contact_name=contact.name)
        except TwinReplyUnavailable:
            is_risky = True
            reason = 'resposta do LLM indisponível'
            evidence = RiskEvidence(
                category='llm_unavailable', snippet='unavailable', source_message_id=message.id,
                source_author=MessageAuthor.UNKNOWN, source_created_at=None, in_current_message=True,
            )
    if not await _owner_audio_after_generation(db, contact, message, instance, _twin_history_digest):
        return
    # Revalidate the human-pause control again right here -- generation
    # (the LLM call above) can take long enough for a pause to happen
    # mid-flight. This does not replace claim_send's own atomic recheck at
    # transport time below; it is a cheap early exit so a reply that is
    # already known-stale is not even enqueued.
    if (await conversation_control.snapshot(db, contact_id, instance))['revision'] != revision:
        await record_log(
            db, source='twin_autopilot', level='info',
            message='Controle humano mudou durante a geração -- resposta descartada antes de enfileirar',
            payload={'contact_id': contact_id, 'instance': instance},
        )
        return
    jobs = JobService(db)
    if is_risky:
        await jobs.enqueue('whatsapp.send_text', {
            'to': contact.phone, 'content': TWIN_HOLDING_MESSAGE, 'is_autopilot_reply': True, 'instance': instance,
            '_twin_contact_id': contact.id, '_twin_source_message_id': message.id,
            '_twin_history_digest': _twin_history_digest, '_twin_revision': revision,
        })
        if settings.whatsapp_owner_alert_phone:
            decision = await decide_owner_alert(
                conversation_control, db, contact_id=contact_id, instance=instance, evidence=evidence,
                window_seconds=settings.whatsapp_twin_loop_guard_window_seconds,
            )
            if decision.should_alert:
                alert = f'[Gêmeo Darius] Mensagem sensível de {contact.name} ({contact.phone}) não foi respondida automaticamente (motivo: {reason}). Responda você mesmo.'
                await record_log(db, source='twin_owner_alert', level='warning', message=alert, payload={'contact_id': contact_id, 'instance': instance, 'dedup_key': decision.key})
                await jobs.enqueue('whatsapp.send_text', {
                    'to': settings.whatsapp_owner_alert_phone, 'content': alert,
                    '_twin_alert_contact_id': contact_id, '_twin_alert_dedup_key': decision.key,
                })
            else:
                await record_log(
                    db, source='twin_owner_alert', level='info',
                    message='Alerta suprimido: mesma evidência (ou paráfrase) já notificada nesta janela',
                    payload={'contact_id': contact_id, 'instance': instance, 'dedup_key': decision.key, 'evidence_group': decision.group},
                )
        log_level, log_message = ('warning', 'Gate de risco acionado — retenção neutra enviada')
        log_payload = {'contact_id': contact_id, 'reason': reason}
    else:
        await jobs.enqueue('whatsapp.send_text', {
            'to': contact.phone, 'content': reply, 'is_autopilot_reply': True, 'instance': instance,
            '_twin_contact_id': contact.id, '_twin_source_message_id': message.id,
            '_twin_history_digest': _twin_history_digest, '_twin_revision': revision,
        })
        log_level, log_message = ('info', 'Resposta impersonada enviada')
        log_payload = {'contact_id': contact_id}
    await _owner_audio_clear_pending(db, contact, _twin_pending_snapshot, instance)
    await db.commit()
    await record_log(db, source='twin_autopilot', level=log_level, message=log_message, payload=log_payload)


def register_event_subscribers() -> None:
    """Wire the handlers above into the Event Bus. Called explicitly from the
    app's startup (not a bare module-level side effect), so tests can
    re-arm this subscription after the per-test event bus reset."""
    event_bus.subscribe("job.failed", _apologize_after_failed_auto_reply)
    event_bus.subscribe("job.failed", _log_failed_staff_notification)


async def _apologize_after_failed_auto_reply(event: Event) -> None:
    """Safety net: if the automatic-reply job exhausts its retries, don't
    leave the contact in silence — send a short apology instead. Demonstrates
    the Event Bus doing real work: this handler has no direct coupling to the
    job worker or the webhook, it only reacts to `job.failed`.
    """
    if event.payload.get("job_name") != "whatsapp.process_inbound":
        return

    job_payload = event.payload.get("job_payload") or {}
    contact_id = job_payload.get("contact_id")
    if contact_id is None:
        return

    async with async_session_factory() as session:
        contact = await ContactRepository(session).get(int(contact_id))
        if contact is None or not contact.phone:
            return
        await JobService(session).enqueue(
            "whatsapp.send_text", {"to": contact.phone, "content": APOLOGY_MESSAGE}
        )


async def _log_failed_staff_notification(event: Event) -> None:
    """Distinct, filterable audit signal for a failed staff-notify send.

    job_event_publisher.publish (jobs/events.py) already writes a
    record_log(level="error", source=f"job:{job.name}") for *every* failed
    job, whatsapp.send_text included -- that part is not silent today. The
    real gap: that generic entry is indistinguishable from any other
    whatsapp.send_text failure (a customer reply, the apology above, ...).
    This adds a specifically-labeled entry only when the failed send was
    the staff notification itself -- the one case where a delivery
    failure means a customer may be waiting with nobody told.
    """
    if event.payload.get("job_name") != "whatsapp.send_text":
        return

    from utils.config import get_settings

    notify_phone = get_settings().store_staff_notify_phone
    job_payload = event.payload.get("job_payload") or {}
    if not notify_phone or job_payload.get("to") != notify_phone:
        return

    async with async_session_factory() as session:
        await record_log(
            session,
            source="store:staff_notify_failed",
            message=(
                f"Aviso à equipe (job {event.payload.get('job_id')}) não foi "
                "entregue após esgotar as tentativas -- um cliente pode estar "
                "aguardando resposta sem que a equipe tenha sido avisada."
            ),
            level="error",
            payload=job_payload,
        )


# Owner-audio context protection
@job_handler('whatsapp.transcribe_owner_audio')
async def transcribe_owner_audio(db: AsyncSession, payload: dict) -> None:
    """Fill only an owner-authored outbound history row; never dispatch a reply."""
    from providers.stt.base import STTProviderError
    from providers.whatsapp.base import InboundMessage
    from utils.config import get_settings
    from webhooks.router import _transcribe_audio
    message = await MessageRepository(db).get(int(payload['message_id']))
    personal_instance = get_settings().evolution_personal_instance
    if message is None or message.direction != MessageDirection.OUTBOUND or message.media_type.value != 'audio' or (not message.sent_by_human) or message.is_autopilot_reply or (not personal_instance) or (message.whatsapp_instance != personal_instance) or (message.content or '').strip():
        return
    media_key = payload.get('media_key')
    if not isinstance(media_key, dict) or media_key.get('fromMe') is not True or (not message.external_id) or (media_key.get('id') != message.external_id):
        raise STTProviderError('Audio do proprietario sem chave de midia correspondente')
    contact = await ContactRepository(db).get(message.contact_id)
    if contact is None:
        return
    inbound = InboundMessage(phone=contact.phone, text='', external_id=message.external_id, media_type='audio', timestamp=message.provider_timestamp, instance=message.whatsapp_instance, media_key=media_key, from_me=True)
    transcript = (await _transcribe_audio(db, get_whatsapp_provider(), inbound)).strip()
    if not transcript:
        raise STTProviderError('Audio do proprietario sem transcricao; verificar midia ou servico de voz')
    await db.refresh(message)
    if message.direction != MessageDirection.OUTBOUND or message.media_type.value != 'audio' or (not message.sent_by_human) or message.is_autopilot_reply or (message.whatsapp_instance != personal_instance) or (message.content or '').strip():
        return
    message.content = transcript
    await db.commit()

def _owner_audio_personal_instance(instance: str | None) -> bool:
    from utils.config import get_settings
    settings = get_settings()
    return bool(settings.evolution_personal_instance) and (
        (instance or settings.evolution_instance or "") == settings.evolution_personal_instance
    )


def _owner_audio_history_content(message) -> str:
    content = message.content or ""
    if (
        message.direction == MessageDirection.OUTBOUND
        and message.sent_by_human
        and message.media_type.value == "audio"
        and _owner_audio_personal_instance(message.whatsapp_instance)
    ):
        if content.strip():
            return "[Áudio enviado pelo proprietário desta conta nesta conversa]\n" + content
        return (
            "[Áudio enviado pelo proprietário desta conta, sem transcrição disponível. "
            "O conteúdo é desconhecido; não deduza o que foi dito.]"
        )
    return content


def _owner_audio_history_digest(history) -> str:
    import hashlib
    import json
    evidence = [
        [m.id, m.direction.value, m.media_type.value, m.content or "",
         bool(m.sent_by_human), bool(m.is_autopilot_reply), m.whatsapp_instance]
        for m in history
    ]
    return hashlib.sha256(json.dumps(evidence, ensure_ascii=False).encode("utf-8")).hexdigest()


async def _owner_audio_refresh_history(db, history, instance) -> None:
    if _owner_audio_personal_instance(instance):
        # The same ORM identity map can otherwise hide a concurrent transcript
        # or correction from the post-generation digest comparison.
        for message in history:
            await db.refresh(message)


async def _owner_audio_context_blocked(db, contact_id, message_id, reason: str) -> None:
    await record_log(
        db,
        source="twin_owner_audio",
        level="warning",
        message="Resposta automática retida para preservar o contexto do proprietário",
        payload={"contact_id": contact_id, "message_id": message_id, "reason": reason},
    )


async def _owner_audio_turn_current(db, contact, message, instance, *, require_awaiting: bool) -> bool:
    from sqlalchemy import and_, func, or_, select
    from models.message import Message
    if not _owner_audio_personal_instance(instance):
        return True
    if (
        not instance or message is None or contact is None
        or message.contact_id != contact.id
        or message.direction != MessageDirection.INBOUND
        or message.whatsapp_instance != instance
    ):
        return False
    await db.refresh(contact)
    if require_awaiting and contact.awaiting_reply_since is None:
        return False
    latest = await MessageRepository(db).get_latest_inbound(contact.id, instance=instance)
    if latest is None or latest.id != message.id:
        return False
    timestamp = message.provider_timestamp or message.created_at
    order_key = func.coalesce(Message.provider_timestamp, Message.created_at)
    newer_human = await db.execute(
        select(Message.id).where(
            Message.contact_id == contact.id,
            Message.whatsapp_instance == instance,
            Message.direction == MessageDirection.OUTBOUND,
            Message.sent_by_human.is_(True),
            or_(order_key > timestamp, and_(order_key == timestamp, Message.id > message.id)),
        ).limit(1)
    )
    return newer_human.scalar_one_or_none() is None


async def _owner_audio_wait_for_history(db, history, contact_id, message_id, instance) -> bool:
    from sqlalchemy import select
    from models.job import Job
    from jobs.owner_audio_dependencies import JobDependencyPending
    from utils.config import get_settings
    if not _owner_audio_personal_instance(instance):
        return True
    for previous in history:
        if not (
            previous.direction == MessageDirection.OUTBOUND
            and previous.sent_by_human
            and not previous.is_autopilot_reply
            and previous.whatsapp_instance == instance
            and previous.media_type.value == "audio"
            and not (previous.content or "").strip()
        ):
            continue
        result = await db.execute(
            select(Job).where(
                Job.name == "whatsapp.transcribe_owner_audio",
                Job.payload["message_id"].as_integer() == previous.id,
            ).order_by(Job.id.desc()).limit(1)
        )
        dependency = result.scalars().first()
        if dependency is None:
            # Legacy rows contain no saved media key and cannot be recovered
            # here. They are represented explicitly by the history formatter.
            continue
        # STT can commit content between the history read and job-state read.
        # Refresh the identity-mapped row before deciding it is still missing.
        await db.refresh(previous)
        if (previous.content or "").strip():
            continue
        state = str(dependency.status.value).lower()
        if state in {"queued", "running"}:
            raise JobDependencyPending(
                f"Owner audio transcription pending for message {previous.id}",
                get_settings().jobs_retry_backoff_seconds,
            )
        # A successful job with blank content is inconsistent, not ready.
        await _owner_audio_context_blocked(
            db, contact_id, message_id,
            f"owner_audio_{state}_without_transcript:{previous.id}",
        )
        return False
    return True


async def _owner_audio_generation_guard(db, contact, message, instance, history) -> bool:
    if not _owner_audio_personal_instance(instance):
        return True
    if not await _owner_audio_turn_current(db, contact, message, instance, require_awaiting=True):
        await _owner_audio_context_blocked(db, contact.id, message.id, "turn_superseded")
        return False
    return await _owner_audio_wait_for_history(db, history, contact.id, message.id, instance)


async def _owner_audio_after_generation(db, contact, message, instance, expected_digest) -> bool:
    from jobs.owner_audio_dependencies import JobDependencyPending
    from utils.config import get_settings
    if not _owner_audio_personal_instance(instance):
        return True
    if not await _owner_audio_turn_current(db, contact, message, instance, require_awaiting=True):
        await _owner_audio_context_blocked(db, contact.id, message.id, "turn_superseded_during_generation")
        return False
    history = await MessageRepository(db).recent_for_contact(contact.id, limit=15, instance=instance)
    await _owner_audio_refresh_history(db, history, instance)
    if not await _owner_audio_wait_for_history(db, history, contact.id, message.id, instance):
        return False
    if _owner_audio_history_digest(history) != expected_digest:
        raise JobDependencyPending("Owner conversation context changed during generation",
                                   get_settings().jobs_retry_backoff_seconds)
    return await _owner_audio_turn_current(db, contact, message, instance, require_awaiting=True)


async def _owner_audio_clear_pending(db, contact, original_marker, instance) -> None:
    if not _owner_audio_personal_instance(instance):
        contact.awaiting_reply_since = None
        return
    from sqlalchemy import update
    # A newer inbound webhook must not have its marker cleared by this turn.
    contact_type = type(contact)
    await db.execute(
        update(contact_type).where(
            contact_type.id == contact.id,
            contact_type.awaiting_reply_since == original_marker,
        ).values(awaiting_reply_since=None).execution_options(synchronize_session=False)
    )


async def _owner_audio_send_guard(db, payload, to, instance) -> bool:
    if not bool(payload.get("is_autopilot_reply")) or not _owner_audio_personal_instance(instance):
        return True
    try:
        contact_id = int(payload["_twin_contact_id"])
        message_id = int(payload["_twin_source_message_id"])
        expected_digest = str(payload["_twin_history_digest"])
    except (KeyError, TypeError, ValueError):
        await _owner_audio_context_blocked(db, None, None, "autopilot_send_missing_context")
        return False
    contact = await ContactRepository(db).get(contact_id)
    message = await MessageRepository(db).get(message_id)
    if contact is None or message is None or str(contact.phone) != to:
        await _owner_audio_context_blocked(db, contact_id, message_id, "send_target_mismatch")
        return False
    if not await _owner_audio_turn_current(db, contact, message, instance, require_awaiting=False):
        await _owner_audio_context_blocked(db, contact_id, message_id, "turn_superseded_before_send")
        return False
    history = await MessageRepository(db).recent_for_contact(contact.id, limit=15, instance=instance)
    await _owner_audio_refresh_history(db, history, instance)
    if not await _owner_audio_wait_for_history(db, history, contact.id, message.id, instance):
        return False
    if _owner_audio_history_digest(history) != expected_digest:
        await _owner_audio_context_blocked(db, contact_id, message_id, "generated_reply_context_changed")
        return False
    return await _owner_audio_turn_current(db, contact, message, instance, require_awaiting=False)
