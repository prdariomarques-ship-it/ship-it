"""Digital twin ("Darius"): writes a reply in the owner's voice.

Deliberately NOT an Agent: no tools, no memory writes, no orchestration -- a
message sent under the owner's identity must not be able to create quotes,
send other messages or touch any data. Just the persona prompt, the recent
conversation and one LLM call (with the Qwen->DeepSeek style fallback), retried
once if the model comes back empty.
"""

import asyncio
import re
import time
from pathlib import Path

from agents.darius_twin_roles import CONTACT_NOT_OWNER, ROLE_RULES, guard_role_inversion
from providers.llm.base import STUB_REPLY, ChatMessage
# `chat_with_fallback` (Qwen -> DeepSeek) existe na fabrica de LLM de PRODUCAO; a candidata ainda nao a tem (ver quadro, G02/E01).
from providers.llm.factory import chat_with_fallback  # type: ignore[attr-defined]
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "darius_twin.md"
_CONVERSATION_PATH = _PROMPT_PATH.with_name("twin_conversation.md")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

# An empty completion is retried exactly once, and only if the retry still fits
# in the job's budget (`jobs_execution_timeout_seconds`, enforced by the worker
# around the whole handler). The margin is left for what the handler does around
# the LLM call: DB reads before it, enqueue + commit + audit log after it. Below
# the minimum a retry could not finish, so it is skipped rather than started.
_EMPTY_RETRY_MARGIN_SECONDS = 30.0
_EMPTY_RETRY_MIN_SECONDS = 10.0


class TwinReplyUnavailable(RuntimeError):
    """The LLM produced nothing usable (empty, or the 'AI unavailable' stub).
    Never send that under the owner's name."""


def load_persona_prompt() -> str:
    text = _PROMPT_PATH.read_text(encoding="utf-8")
    conversation = _CONVERSATION_PATH.read_text(encoding="utf-8")
    return _HTML_COMMENT.sub("", text).strip() + "\n\n" + conversation.strip() + "\n\n" + ROLE_RULES


async def generate_darius_reply(
    history: list[ChatMessage],
    message: str,
    *,
    contact_name: str = "",
    extra_system: list[str] | None = None,
) -> str:
    """`history` is the conversation BEFORE `message` (user = the contact,
    assistant = the owner/twin); `message` is the pending inbound text.
    `contact_name` is the contact's saved name (Contact.name) -- the persona
    prompt has always had "[nome]" placeholders in its example replies (see
    "Identificação do contato" / examples like "Bom dia, [nome]") but nothing
    ever told the model who it was actually talking to until this parameter
    was added (2026-09-21 review).

    `extra_system` (optional) are additional system blocks built by the caller
    (e.g. style examples retrieved for this message -- see
    `agents/darius_twin_context.py`). They are context, never facts."""
    messages = [ChatMessage(role="system", content=load_persona_prompt())]
    if contact_name:
        messages.append(
            ChatMessage(
                role="system",
                content=f"Você está respondendo, pelo WhatsApp, para: {contact_name}." + CONTACT_NOT_OWNER,
            )
        )
    for block in extra_system or []:
        messages.append(ChatMessage(role="system", content=block))
    messages.extend(history)
    messages.append(ChatMessage(role="user", content=message))
    started = time.monotonic()
    result = await chat_with_fallback(messages, tools=None)
    reply = (result.content or "").strip()
    if not reply:
        reply = await _retry_once_after_empty(messages, started)
    if not reply or reply == STUB_REPLY or reply.startswith("[IA indispon"):
        raise TwinReplyUnavailable("LLM returned no usable reply")
    # Rede de segurança dos papéis (agents/darius_twin_roles.py): o contato perguntou pelo dono e nunca disse estar doente -> a pergunta de
    # saúde devolvida a ele sai da resposta. Se não sobrar nada, é "sem resposta utilizável" (retenção neutra), nunca um texto invertido.
    contact_texts = [m.content for m in history if m.role == "user"]
    guarded = guard_role_inversion(
        reply, message, contact_texts, drop_health_question=get_settings().twin_role_guard_enabled
    )
    if guarded != reply:
        logger.warning("Twin reply adjusted by the role-inversion guard")
    if not guarded:
        raise TwinReplyUnavailable("reply was only a health question returned to the contact")
    return guarded


async def _retry_once_after_empty(messages: list[ChatMessage], started: float) -> str:
    """One more LLM call after an empty completion, bounded by what is left of
    the job budget. Returns "" when there is no time left, when the retry is
    empty too, or when it overruns -- the caller then raises
    TwinReplyUnavailable and the neutral holding message goes out; a reply is
    never forced under the owner's name. Only an empty completion is retried:
    the 'AI unavailable' stub and provider exceptions keep their old handling
    (an exception from the retry propagates like one from the first call)."""
    remaining = (
        get_settings().jobs_execution_timeout_seconds
        - _EMPTY_RETRY_MARGIN_SECONDS
        - (time.monotonic() - started)
    )
    if remaining < _EMPTY_RETRY_MIN_SECONDS:
        logger.warning(
            "Twin LLM returned an empty reply; no retry (%.0fs of job budget left)",
            max(remaining, 0.0),
        )
        return ""
    logger.warning(
        "Twin LLM returned an empty reply; retrying once (%.0fs of job budget left)",
        remaining,
    )
    try:
        result = await asyncio.wait_for(
            chat_with_fallback(messages, tools=None), timeout=remaining
        )
    except asyncio.TimeoutError:
        logger.warning("Twin LLM retry did not finish within the job budget")
        return ""
    return (result.content or "").strip()
