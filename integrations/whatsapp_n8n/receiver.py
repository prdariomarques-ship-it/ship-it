#!/usr/bin/env python3
"""
Evolution API → SQLite buffer → n8n Executive Summary

FastAPI service with three endpoints:

  POST /webhook/evolution
      Receives MESSAGES_UPSERT events from Evolution API.
      Normalises text + audio-transcript messages, deduplicates by msg_id,
      stores in SQLite buffer. Returns 200 immediately.

  POST /api/flush
      Called by n8n Schedule Trigger (or manually).
      Reads buffered messages for the configured time window, runs LLM
      synthesis, marks them processed, and returns the summary payload
      as JSON so n8n can continue the workflow inline.

  GET /api/status
      Buffer health stats (total / pending / last flush).

Run:
    uvicorn receiver:app --host 0.0.0.0 --port 8001 --reload

Environment variables:
    RECEIVER_HOST             – bind host          (default: 0.0.0.0)
    RECEIVER_PORT             – bind port          (default: 8001)
    EVOLUTION_WEBHOOK_TOKEN   – secret token from Evolution API config;
                                when set, every /webhook/evolution POST
                                must carry it in X-Api-Key or apikey body field
    N8N_API_KEY               – protects /api/flush (same key n8n sends as x-api-key)
    BUFFER_WINDOW_HOURS       – hours to look back on flush (default: 8)
    BUFFER_DB_PATH            – SQLite file path (default: ./whatsapp_buffer.db)
    LLM_PROVIDER              – 'anthropic' (default) | 'gemini'
    LLM_MODEL                 – model override
    ANTHROPIC_API_KEY         – Claude API key
    GEMINI_API_KEY            – Gemini API key
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

# Sibling-module imports (run from the same directory)
import buffer as buf
from whatsapp_executive_summary import (
    RawMessage,
    build_n8n_payload,
    generate_summary,
    load_messages,
    N8N_WEBHOOK_URL,
    N8N_API_KEY,
    post_to_n8n,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EVOLUTION_WEBHOOK_TOKEN: str = os.getenv("EVOLUTION_WEBHOOK_TOKEN", "")
FLUSH_API_KEY: str = N8N_API_KEY  # reuse the same secret for the flush endpoint
BUFFER_WINDOW_HOURS: float = float(os.getenv("BUFFER_WINDOW_HOURS", "8"))

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="WhatsApp Executive Summary Receiver",
    description="Evolution API ingest + n8n flush endpoint",
    version="2.0.0",
)


@app.on_event("startup")
async def _startup() -> None:
    buf.init_db()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _verify_evolution_token(body: dict, x_api_key: str | None) -> None:
    """Validate the Evolution API shared secret when EVOLUTION_WEBHOOK_TOKEN is set."""
    if not EVOLUTION_WEBHOOK_TOKEN:
        return  # auth disabled in dev mode
    provided = x_api_key or body.get("apikey", "")
    if provided != EVOLUTION_WEBHOOK_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Evolution API token.",
        )


def _verify_flush_key(x_api_key: str | None) -> None:
    """Validate the n8n API key on /api/flush when N8N_API_KEY is set."""
    if not FLUSH_API_KEY:
        return  # auth disabled in dev mode
    if x_api_key != FLUSH_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key for flush endpoint.",
        )


# ---------------------------------------------------------------------------
# Evolution API payload normaliser
# ---------------------------------------------------------------------------

def _extract_phone(jid: str) -> str:
    """Strip '@s.whatsapp.net' / '@g.us' and return the digits-only identifier."""
    return jid.split("@")[0]


def _normalise_event(event: dict) -> dict | None:
    """
    Convert a raw Evolution API MESSAGES_UPSERT event into a flat dict
    suitable for the buffer, or return None to discard.

    Discards:
      - non-upsert event types
      - messages sent by the account owner (fromMe=true)
      - media types we can't process (image, sticker, video, …) that have
        no text or transcription
    """
    if event.get("event") not in ("messages.upsert", "MESSAGES_UPSERT"):
        return None

    data: dict = event.get("data", {})
    key: dict = data.get("key", {})

    if key.get("fromMe", False):
        return None  # own messages are noise

    msg_id: str = key.get("id", "")
    remote_jid: str = key.get("remoteJid", "")
    is_group: bool = remote_jid.endswith("@g.us")

    # For group messages, the real sender is in key.participant
    sender_jid: str = (
        key.get("participant", remote_jid) if is_group else remote_jid
    )
    sender_phone: str = _extract_phone(sender_jid)
    push_name: str = data.get("pushName", sender_phone)
    sender_label: str = push_name + (" (Grupo)" if is_group else "")

    msg_type_raw: str = data.get("messageType", "")
    message: dict = data.get("message", {})
    timestamp_seconds: int = int(data.get("messageTimestamp", 0))
    received_at: str = (
        datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc).isoformat()
        if timestamp_seconds
        else datetime.now(timezone.utc).isoformat()
    )

    # --- Extract text content ---
    text: str = ""
    msg_type: str = "text"

    if msg_type_raw == "conversation":
        text = message.get("conversation", "")

    elif msg_type_raw == "extendedTextMessage":
        text = message.get("extendedTextMessage", {}).get("text", "")

    elif msg_type_raw == "audioMessage":
        # Prefer Whisper transcription if present
        transcript: str = data.get("speechToText", "").strip()
        if transcript:
            text = f"[Áudio transcrição] {transcript}"
            msg_type = "audio_transcript"
        else:
            duration: int = message.get("audioMessage", {}).get("seconds", 0)
            if duration < 3:
                return None  # too short to be meaningful
            text = f"[Áudio de {duration}s — transcrição não disponível]"
            msg_type = "audio_transcript"

    else:
        # Unsupported type (image, video, sticker, …) — skip unless there's a caption
        caption: str = (
            message.get(msg_type_raw, {}).get("caption", "")
            if isinstance(message.get(msg_type_raw), dict)
            else ""
        )
        if not caption:
            return None
        text = caption

    if not text.strip():
        return None

    # Build stable fallback ID if provider sent no ID
    if not msg_id:
        msg_id = buf.make_fallback_id(sender_phone, text, timestamp_seconds)

    return {
        "msg_id": msg_id,
        "sender": sender_label,
        "sender_phone": sender_phone,
        "text": text.strip(),
        "received_at": received_at,
        "msg_type": msg_type,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/webhook/evolution", status_code=200)
async def receive_evolution(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
) -> JSONResponse:
    """
    Ingest a single MESSAGES_UPSERT event (or an array of events) from
    Evolution API. Accepts both the v1 single-event shape and the v2
    batch-array shape.
    """
    try:
        body: Any = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    # Support both single event and array
    events: list[dict] = body if isinstance(body, list) else [body]

    _verify_evolution_token(events[0] if events else {}, x_api_key)

    inserted = 0
    skipped_noise = 0
    skipped_dup = 0

    for event in events:
        normalised = _normalise_event(event)
        if normalised is None:
            skipped_noise += 1
            continue

        added = buf.add_message(**normalised)
        if added:
            inserted += 1
        else:
            skipped_dup += 1

    return JSONResponse({
        "status": "ok",
        "inserted": inserted,
        "skipped_noise": skipped_noise,
        "skipped_duplicate": skipped_dup,
    })


@app.post("/api/flush")
async def flush_buffer(
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    window_hours: float | None = None,
    trigger: str = "api",
    mock_llm: bool = False,
) -> JSONResponse:
    """
    Process all pending buffer messages within the time window:
      1. Load from SQLite
      2. Apply noise filter
      3. Call LLM for executive summary
      4. Mark messages processed
      5. Return the summary payload (same shape as the Webhook Receiver path)

    n8n Schedule Trigger calls this endpoint; the workflow continues with
    the JSON response directly (no second webhook POST needed).

    Query params:
      window_hours – override BUFFER_WINDOW_HOURS for this flush
      trigger      – label for the flush_log ('schedule' | 'manual' | 'api')
      mock_llm     – use built-in mock summary (for testing without API keys)
    """
    _verify_flush_key(x_api_key)

    effective_window = window_hours or BUFFER_WINDOW_HOURS

    # --- load from buffer ---
    pending = buf.get_pending(window_hours=effective_window)

    if not pending:
        return JSONResponse({
            "event": "whatsapp_executive_summary",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stats": {
                "total_messages_processed": 0,
                "unique_senders": 0,
                "senders": [],
            },
            "summary_markdown": "ℹ️ Nenhuma mensagem pendente no buffer para este período.",
            "metadata": {
                "trigger": trigger,
                "window_hours": effective_window,
                "buffer_empty": True,
            },
        })

    # --- convert buffer rows to RawMessage objects (reuse noise filter) ---
    raw_list = [
        {
            "timestamp": row["received_at"],
            "sender": row["sender"],
            "text": row["text"],
        }
        for row in pending
    ]
    messages: list[RawMessage] = load_messages(raw_list)

    if not messages:
        buf.log_flush(0, effective_window, trigger)
        return JSONResponse({
            "event": "whatsapp_executive_summary",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stats": {
                "total_messages_processed": 0,
                "unique_senders": 0,
                "senders": [],
            },
            "summary_markdown": "ℹ️ Nenhuma ação ou decisão pendente identificada nas mensagens analisadas.",
            "metadata": {
                "trigger": trigger,
                "window_hours": effective_window,
                "buffer_rows_before_noise_filter": len(pending),
            },
        })

    # --- LLM synthesis ---
    summary = generate_summary(messages, mock=mock_llm)

    # --- mark processed + log ---
    processed_ids = [row["msg_id"] for row in pending]
    buf.mark_processed(processed_ids)
    buf.log_flush(len(messages), effective_window, trigger)

    # --- build and return payload ---
    payload = build_n8n_payload(summary, messages, webhook_url="(inline-response)")
    payload["metadata"]["trigger"] = trigger
    payload["metadata"]["window_hours"] = effective_window
    payload["metadata"]["buffer_rows_flushed"] = len(pending)

    return JSONResponse(payload)


@app.get("/api/status")
async def buffer_status(
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
) -> JSONResponse:
    """Return buffer health stats."""
    _verify_flush_key(x_api_key)
    stats = buf.get_stats()
    stats["buffer_db_path"] = buf.BUFFER_DB_PATH
    stats["buffer_window_hours"] = BUFFER_WINDOW_HOURS
    return JSONResponse(stats)


# ---------------------------------------------------------------------------
# Dev runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("RECEIVER_HOST", "0.0.0.0")
    port = int(os.getenv("RECEIVER_PORT", "8001"))
    uvicorn.run("receiver:app", host=host, port=port, reload=True)
