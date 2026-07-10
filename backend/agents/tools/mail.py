"""Gmail tools — Sprint 1. Read-only: search, read a thread, summarize a
long thread, detect pending actions. Sending, replying, moving and deleting
are explicitly out of scope; creating a task/event *from* an email still
goes through the existing `create_task`/`create_event` tools, triggered only
when the owner asks for it in the conversation — this file never calls them
itself.

Registered only on `agents/assistant_agent.py`. No other agent gets these —
the Email domain has exactly one technical gateway. A specialized agent
(Investimentos, Loja, Igreja) that needs something from email gets it
through a Cognitive Planner multi-step plan that routes one step to
`assistant`, never through direct tool access — see `docs/EMAIL.md`.
"""
from datetime import datetime, timedelta, timezone

from agents.tools.base import Tool, ToolContext, ok
from providers.llm.base import ChatMessage, ToolSpec
from providers.llm.factory import get_llm_provider
from providers.mail.base import EmailSearchQuery, MailProviderError
from providers.mail.factory import get_mail_provider
from repositories.email_account import EmailAccountRepository
from services.token_crypto import TokenEncryptionNotConfigured, decrypt_token


class MailNotConnectedError(RuntimeError):
    """No Gmail account authorized for this user — surfaced to the model as
    a normal tool error (via Tool.run's catch-all), same as any other tool
    failure. Never a crash, never a fallback to someone else's mailbox."""


async def _get_access_token(context: ToolContext) -> str:
    """The only place a mailbox is chosen — always from `context.user.id`
    (set by the application, never by the model). This is the same
    principle established by PROD-005 for WhatsApp contacts, applied to the
    Email domain: authorization lives in code, never only in a prompt."""
    if context.user is None:
        raise MailNotConnectedError("No authenticated user in context")

    provider = get_mail_provider()
    account = await EmailAccountRepository(context.db).get_by_user(context.user.id, provider.name)
    if account is None:
        raise MailNotConnectedError(
            "Nenhuma conta de e-mail conectada. Peça ao administrador para conectar em /api/mail/connect."
        )
    try:
        refresh_token = decrypt_token(account.encrypted_refresh_token)
    except TokenEncryptionNotConfigured as exc:
        raise MailNotConnectedError(str(exc)) from exc

    try:
        tokens = await provider.refresh_access_token(refresh_token)
    except MailProviderError as exc:
        # A revoked/expired refresh token (e.g. the user pulled access in
        # myaccount.google.com/permissions) is functionally "not connected"
        # from here on — surface the same actionable message instead of a
        # raw provider error, so the model tells the owner how to fix it.
        raise MailNotConnectedError(
            "A conexão com o Gmail expirou ou foi revogada. Peça ao administrador para "
            "reconectar em /api/mail/connect."
        ) from exc
    return tokens.access_token


def _parse_date(value: str | None) -> datetime | None:
    """Accepts the documented date-only contract (YYYY-MM-DD, naive — gets
    UTC attached) and, defensively, a full ISO datetime with its own offset
    (converted to UTC instead of having that offset silently overwritten)."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def _search_emails(
    context: ToolContext,
    sender: str | None = None,
    subject: str | None = None,
    since: str | None = None,
    until: str | None = None,
    keywords: str | None = None,
    labels: list[str] | None = None,
    limit: int = 20,
) -> str:
    access_token = await _get_access_token(context)
    provider = get_mail_provider()
    query = EmailSearchQuery(
        sender=sender,
        subject=subject,
        since=_parse_date(since),
        until=_parse_date(until),
        keywords=keywords,
        labels=labels or [],
        limit=min(limit, 50),
    )
    try:
        messages = await provider.search(access_token, query)
    except MailProviderError as exc:
        raise RuntimeError(f"Falha ao buscar e-mails: {exc}") from exc

    return ok(
        messages=[
            {
                "id": message.id,
                "thread_id": message.thread_id,
                "sender": message.sender,
                "subject": message.subject,
                "snippet": message.snippet,
                "date": message.date,
                "labels": message.labels,
            }
            for message in messages
        ]
    )


_MAX_BODY_CHARS = 3000  # keep a long thread from blowing out the conversation context


async def _read_email_thread(context: ToolContext, thread_id: str) -> str:
    access_token = await _get_access_token(context)
    provider = get_mail_provider()
    try:
        thread = await provider.get_thread(access_token, thread_id)
    except MailProviderError as exc:
        raise RuntimeError(f"Falha ao ler a conversa: {exc}") from exc

    return ok(
        thread_id=thread.id,
        subject=thread.subject,
        messages=[
            {
                "id": message.id,
                "sender": message.sender,
                "date": message.date,
                "body": message.body[:_MAX_BODY_CHARS],
            }
            for message in thread.messages
        ],
    )


_SUMMARY_PROMPT = (
    "Você resume uma conversa de e-mail para o Dario OS. Leia a troca de mensagens abaixo "
    "e escreva um resumo conciso (no máximo 6 frases) do que foi discutido, decisões tomadas "
    "e qualquer pendência aberta. Responda apenas com o resumo, em português brasileiro."
)


async def _summarize_email_thread(context: ToolContext, thread_id: str) -> str:
    access_token = await _get_access_token(context)
    provider = get_mail_provider()
    try:
        thread = await provider.get_thread(access_token, thread_id)
    except MailProviderError as exc:
        raise RuntimeError(f"Falha ao ler a conversa: {exc}") from exc

    if not thread.messages:
        return ok(summary="", subject=thread.subject)

    transcript = "\n\n".join(
        f"De: {message.sender}\nData: {message.date}\n{message.body[:_MAX_BODY_CHARS]}"
        for message in thread.messages
    )
    result = await get_llm_provider().chat(
        [
            ChatMessage(role="system", content=_SUMMARY_PROMPT),
            ChatMessage(role="user", content=f"Assunto: {thread.subject}\n\n{transcript}"),
        ]
    )
    return ok(summary=result.content.strip(), subject=thread.subject)


_ACTION_TYPES = ["respond", "send_proposal", "schedule_meeting", "other"]

_DETECT_ACTIONS_TOOL = ToolSpec(
    name="report_pending_actions",
    description=(
        "Registra as ações pendentes identificadas nos e-mails analisados — "
        "uma lista vazia é uma resposta válida quando nada está pendente."
    ),
    parameters={
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": _ACTION_TYPES},
                        "description": {"type": "string"},
                        "thread_id": {"type": "string"},
                        "subject": {"type": "string"},
                    },
                    "required": ["type", "description", "thread_id"],
                },
            }
        },
        "required": ["actions"],
    },
)

_DETECT_PROMPT = (
    "Você analisa uma lista de e-mails recentes do Dario OS e identifica ações pendentes: "
    "mensagens que esperam uma resposta, pedem o envio de uma proposta, mencionam ou pedem "
    "o agendamento de uma reunião, ou outra pendência clara. Chame report_pending_actions "
    "com a lista encontrada (vazia se nada estiver pendente). Não invente pendências que não "
    "estejam explícitas no texto."
)


async def _detect_pending_actions(context: ToolContext, since_days: int = 7, limit: int = 20) -> str:
    access_token = await _get_access_token(context)
    provider = get_mail_provider()
    since = datetime.now(timezone.utc) - timedelta(days=max(since_days, 1))
    try:
        messages = await provider.search(access_token, EmailSearchQuery(since=since, limit=min(limit, 50)))
    except MailProviderError as exc:
        raise RuntimeError(f"Falha ao buscar e-mails: {exc}") from exc

    if not messages:
        return ok(actions=[])

    transcript = "\n".join(
        f"- [{message.thread_id}] De: {message.sender} | Assunto: {message.subject} | {message.snippet}"
        for message in messages
    )
    result = await get_llm_provider().chat(
        [
            ChatMessage(role="system", content=_DETECT_PROMPT),
            ChatMessage(role="user", content=transcript),
        ],
        tools=[_DETECT_ACTIONS_TOOL],
    )
    call = next((c for c in result.tool_calls if c.name == "report_pending_actions"), None)
    if call is None:
        return ok(actions=[])
    return ok(actions=call.arguments.get("actions", []))


search_emails_tool = Tool(
    name="search_emails",
    description="Busca e-mails na caixa de entrada conectada por remetente, assunto, período, palavras-chave ou etiqueta.",
    handler=_search_emails,
    parameters={
        "type": "object",
        "properties": {
            "sender": {"type": "string", "description": "E-mail ou nome do remetente"},
            "subject": {"type": "string"},
            "since": {"type": "string", "description": "Data ISO (YYYY-MM-DD), início do período"},
            "until": {"type": "string", "description": "Data ISO (YYYY-MM-DD), fim do período"},
            "keywords": {"type": "string", "description": "Palavras-chave livres"},
            "labels": {"type": "array", "items": {"type": "string"}},
            "limit": {"type": "integer", "description": "Máximo de resultados (padrão 20)"},
        },
        "required": [],
    },
)

read_email_thread_tool = Tool(
    name="read_email_thread",
    description="Lê o conteúdo completo de uma conversa de e-mail (todas as mensagens) pelo id da thread.",
    handler=_read_email_thread,
    parameters={
        "type": "object",
        "properties": {"thread_id": {"type": "string"}},
        "required": ["thread_id"],
    },
)

summarize_email_thread_tool = Tool(
    name="summarize_email_thread",
    description="Resume uma conversa de e-mail longa em poucas frases, incluindo pendências.",
    handler=_summarize_email_thread,
    parameters={
        "type": "object",
        "properties": {"thread_id": {"type": "string"}},
        "required": ["thread_id"],
    },
)

detect_pending_email_actions_tool = Tool(
    name="detect_pending_email_actions",
    description=(
        "Analisa os e-mails recentes e identifica ações pendentes: responder, enviar proposta, "
        "agendar reunião, ou outra pendência clara."
    ),
    handler=_detect_pending_actions,
    parameters={
        "type": "object",
        "properties": {
            "since_days": {"type": "integer", "description": "Quantos dias para trás analisar (padrão 7)"},
            "limit": {"type": "integer", "description": "Máximo de e-mails a analisar (padrão 20)"},
        },
        "required": [],
    },
)
