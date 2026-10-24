"""Twin (Darius) context helpers: untranscribed owner audio and received-but-unreadable media.

Production facts (jobs/handlers.py::twin_autopilot_check):
  * an owner audio without transcript reaches the LLM as the marker "[Áudio enviado pelo proprietário ...
    sem transcrição ... não deduza o que foi dito]" and the model invented the content anyway
    (11974, 12012 "A irmã Fátima falou ..."). Prompt rules did not stop it -> gate in code;
  * inbound images have empty content and are dropped from the twin history, so the model said
    "não chegou foto nenhuma" about photos that were registered (11991 vs 11982-11984).

Pure functions over Message-like rows (no DB, no settings).
"""

from __future__ import annotations

OWNER_AUDIO_LABEL = "[Áudio enviado pelo proprietário desta conta nesta conversa]\n"
MEDIA_WITH_NO_TEXT = {"image", "video", "document", "sticker"}
_LABEL = {"image": "uma imagem", "video": "um vídeo", "document": "um documento", "sticker": "uma figurinha"}


def _val(x) -> str:
    return str(getattr(x, "value", x)).lower()


def _stamp(row):
    return getattr(row, "provider_timestamp", None) or getattr(row, "created_at", None)


def _chronological(rows):
    rows = list(rows)
    try:
        return sorted(rows, key=lambda r: (_stamp(r), r.id))
    except TypeError:
        return sorted(rows, key=lambda r: r.id)


def _is_owner_turn(row) -> bool:
    return (_val(row.direction) == "outbound" and bool(getattr(row, "sent_by_human", False))
            and not bool(getattr(row, "is_autopilot_reply", False)))


def last_owner_turn_is_untranscribed_audio(history, current_message_id: int) -> bool:
    """True when the most recent message the OWNER sent himself (before the inbound being answered) is an
    audio with no transcript: the twin cannot know what he said and must not answer on his behalf."""
    owner_rows = [r for r in _chronological(history) if r.id < current_message_id and _is_owner_turn(r)]
    if not owner_rows:
        return False
    last = owner_rows[-1]
    return _val(last.media_type) == "audio" and not (getattr(last, "content", "") or "").strip()


def twin_history_content(row, base: str) -> str:
    """`base` is what `_owner_audio_history_content(row)` returned. Keep it when there is any; otherwise an
    inbound media message without text becomes an explicit 'received, unreadable' line instead of vanishing."""
    if base:
        # The owner's own audio reaches the model as an ASSISTANT turn. Its "[Áudio enviado pelo proprietário...]"
        # label was copied into replies (11974, 12012, 12033, 12160, 12259, 12270): in assistant-role turns send the
        # transcript only. (The "sem transcrição" marker is kept: the untranscribed-audio gate and the output guard
        # cover it.)
        if _val(row.direction) == "outbound" and base.startswith(OWNER_AUDIO_LABEL):
            return base[len(OWNER_AUDIO_LABEL):].strip() or base
        return base
    media = _val(getattr(row, "media_type", "text"))
    if _val(row.direction) == "inbound" and media in MEDIA_WITH_NO_TEXT and not (getattr(row, "content", "") or "").strip():
        return (f"[O contato enviou {_LABEL[media]}. O arquivo foi recebido e está registrado, mas você não "
                "consegue ver o conteúdo. Não diga que não chegou; pode dizer que recebeu e pedir que o contato "
                "explique por texto ou áudio do que se trata.]")
    return ""
