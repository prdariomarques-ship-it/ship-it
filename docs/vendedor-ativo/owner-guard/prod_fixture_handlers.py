"""FIXTURE: trechos EXATOS de /app/jobs/handlers.py da produção (colados em 18/10/2026; linhas 175-197 e 248-365), com um cabeçalho mínimo
de imports/stubs para os testes. Serve de base para testar as edições ancoradas de `aplicar_owner_guard.py` contra o texto real."""
from sqlalchemy.ext.asyncio import AsyncSession

from models.message import MessageDirection


def job_handler(name):
    return lambda fn: fn


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
    provider (and a call with no `instance`) behaves exactly as before."""
    from providers.whatsapp.evolution.provider import EvolutionProvider
    to = str(payload['to'])
    content = str(payload['content'])
    instance = payload.get('instance') or None
    if not await _owner_audio_send_guard(db, payload, to, instance):
        return
    provider = get_whatsapp_provider()
    if instance and isinstance(provider, EvolutionProvider):
        await provider.send_text(to, content, instance=instance)
    else:
        await provider.send_text(to, content)
    await persist_outbound_message(db, to, content, is_autopilot_reply=bool(payload.get('is_autopilot_reply')), instance=instance)


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
        from providers.llm.base import ChatMessage
        from services.extra_agent_history import build_extra_agent_history
        _recent = await MessageRepository(db).recent_for_contact(contact_id, limit=40, instance=instance)
        _history = [ChatMessage(role=r, content=c) for r, c in build_extra_agent_history(_recent, message)]
        result = await ai_orchestrator.run(
            db=db, user=owner, message=message.content,
            agent_name=extra_agents[instance], contact_id=None,
            memories=[], history=_history,
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
