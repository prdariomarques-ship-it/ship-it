#!/usr/bin/env python3
"""
WhatsApp → Executive Summary → n8n

Reads a batch of raw WhatsApp messages, strips informal noise, synthesises a
strictly executive summary via Claude/Gemini, then POSTs the result to an n8n
Webhook node.

Usage:
    # From a JSON file
    python whatsapp_executive_summary.py --input messages.json

    # From stdin (pipe)
    cat messages.json | python whatsapp_executive_summary.py --stdin

    # With a custom webhook URL
    python whatsapp_executive_summary.py --input messages.json \
        --webhook https://your-n8n.example.com/webhook/XXXX

Environment variables (override CLI flags):
    N8N_WEBHOOK_URL   – full n8n webhook endpoint
    N8N_API_KEY       – shared-secret header for webhook auth
    ANTHROPIC_API_KEY – Claude API key  (used when LLM_PROVIDER=anthropic)
    GEMINI_API_KEY    – Gemini API key  (used when LLM_PROVIDER=gemini)
    LLM_PROVIDER      – "anthropic" (default) | "gemini"
    LLM_MODEL         – model override (defaults per provider below)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"  # latest capable model
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"

N8N_WEBHOOK_URL: str = os.getenv("N8N_WEBHOOK_URL", "")
N8N_API_KEY: str = os.getenv("N8N_API_KEY", "")
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic").lower()
LLM_MODEL: str = os.getenv("LLM_MODEL", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

REQUEST_TIMEOUT = 120  # seconds


# ---------------------------------------------------------------------------
# Data models (plain dataclasses — no FastAPI dependency needed here)
# ---------------------------------------------------------------------------

class RawMessage:
    __slots__ = ("timestamp", "sender", "text")

    def __init__(self, timestamp: str, sender: str, text: str) -> None:
        self.timestamp = timestamp
        self.sender = sender.strip()
        self.text = text.strip()

    def __repr__(self) -> str:
        return f"RawMessage(sender={self.sender!r}, ts={self.timestamp!r})"


# ---------------------------------------------------------------------------
# Pre-processing: load and clean
# ---------------------------------------------------------------------------

_NOISE_PATTERNS = [
    r"(?i)^(oi|olá|boa\s*(tarde|manhã|noite)|bom\s*dia|e\s+aí|tudo\s*bem)[!?.,\s]*$",
    r"(?i)^(ok|okay|certo|entendido|perfeito|ótimo|beleza|vlw|valeu|obrigado|obg)[!?.,\s]*$",
    r"(?i)^\s*👍+\s*$",
    r"(?i)^(sim|não|claro|com\s*certeza|exato)[!?.,\s]*$",
]
_NOISE_RE = [re.compile(p) for p in _NOISE_PATTERNS]

_MIN_TEXT_LENGTH = 10  # messages shorter than this after stripping are noise


def _is_noise(text: str) -> bool:
    text = text.strip()
    if len(text) < _MIN_TEXT_LENGTH:
        return True
    return any(r.match(text) for r in _NOISE_RE)


def load_messages(raw: Any) -> list[RawMessage]:
    """Parse and clean the input payload into RawMessage objects."""
    if not isinstance(raw, list):
        raise ValueError("Input must be a JSON array of message objects.")

    messages: list[RawMessage] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Item at index {i} is not a JSON object.")
        ts = str(item.get("timestamp") or item.get("time") or item.get("date") or "")
        sender = str(item.get("sender") or item.get("from") or item.get("name") or "Desconhecido")
        text = str(item.get("text") or item.get("message") or item.get("body") or "")
        if not text or _is_noise(text):
            continue
        messages.append(RawMessage(timestamp=ts, sender=sender, text=text))

    return messages


def format_for_prompt(messages: list[RawMessage]) -> str:
    """Serialise cleaned messages into the prompt-ready block."""
    lines: list[str] = []
    for m in messages:
        ts_tag = f"[{m.timestamp}] " if m.timestamp else ""
        lines.append(f"{ts_tag}{m.sender}: {m.text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Synthesis prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Você é um assistente executivo de altíssima performance.
Sua única função é transformar um lote de mensagens brutas do WhatsApp em um
resumo diário ESTRITAMENTE executivo, sem perda de informação relevante.

REGRAS OBRIGATÓRIAS DE SÍNTESE:
1. Ignore completamente cumprimentos, saudações, "ok", "certo", emojis isolados
   e qualquer conteúdo informal sem valor decisório.
2. Agrupe por Remetente/Canal.
3. Para cada remetente com conteúdo relevante, produza EXATAMENTE estas três linhas:
   📌 *Assunto Principal:* <máximo 1 frase objetiva>
   ⚡ *Ações / Pendências:* <o que exige resposta, decisão ou aprovação — use lista com •>
   📊 *Dados:* <porcentagens, valores monetários, prazos, indicadores — "N/A" se ausente>
4. Finalize com o bloco isolado:
   🚨 *AÇÕES IMEDIATAS PRIORITÁRIAS*
   Liste as 3-5 itens que exigem ação HOJE, em ordem de urgência.
5. Use Markdown compatível com Telegram/WhatsApp (*negrito*, _itálico_, listas com •).
6. Não adicione introduções, despedidas, contexto extra ou opiniões.
7. Se não houver conteúdo executivo real, responda apenas:
   ℹ️ Nenhuma ação ou decisão pendente identificada nas mensagens analisadas."""

USER_PROMPT_TEMPLATE = """DATA DO BRIEFING: {date}
TOTAL DE MENSAGENS FILTRADAS: {count}

--- MENSAGENS ---
{messages}
--- FIM ---

Gere o resumo executivo agora."""


def build_user_prompt(messages: list[RawMessage]) -> str:
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    body = format_for_prompt(messages)
    return USER_PROMPT_TEMPLATE.format(date=today, count=len(messages), messages=body)


# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------

def _call_anthropic(user_prompt: str, model: str) -> str:
    if not ANTHROPIC_API_KEY:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set.")
    model = model or DEFAULT_ANTHROPIC_MODEL
    payload = {
        "model": model,
        "max_tokens": 2048,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        resp = client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
        resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"]


def _call_gemini(user_prompt: str, model: str) -> str:
    if not GEMINI_API_KEY:
        raise EnvironmentError("GEMINI_API_KEY is not set.")
    model = model or DEFAULT_GEMINI_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.2},
    }
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        resp = client.post(url, json=payload, params={"key": GEMINI_API_KEY})
        resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


_MOCK_SUMMARY = """\
*Carlos Mendes*
📌 *Assunto Principal:* Aprovação urgente de contrato com Infraco — R$ 2.400.000.
⚡ *Ações / Pendências:*
• Aprovar ou rejeitar proposta até 11/08 (deadline da contraparte: 12/08)
📊 *Dados:* Valor total R$ 2.400.000 · Prazo de assinatura 12/08/2026

---
*Ana Paula – Financeiro*
📌 *Assunto Principal:* EBITDA de julho abaixo do target; solicitação de realocação de budget.
⚡ *Ações / Pendências:*
• Aprovar redirecionamento de R$ 180k de mídia paga para inbound
📊 *Dados:* Margem EBITDA jul/26 = 18,3% (target 22%) · CAC digital +34% · Realocação R$ 180k

---
*Rodrigo – Tech Lead*
📌 *Assunto Principal:* Vulnerabilidade crítica de autenticação com hotfix pronto para deploy.
⚡ *Ações / Pendências:*
• Aprovar deploy em produção hoje às 14h
📊 *Dados:* CVE pendente · Deploy agendado 14h de hoje

---
*Fernanda – RH*
📌 *Assunto Principal:* Três ofertas de emprego aguardando assinatura digital até 10/08.
⚡ *Ações / Pendências:*
• Assinar digitalmente as 3 ofertas no sistema de RH até sexta (10/08)
📊 *Dados:* Gerente Produto R$ 18k · Engenheiro Sênior R$ 22k · Designer UX R$ 12k · Total headcount +R$ 52k/mês

---
*Marcos – Vendas*
📌 *Assunto Principal:* 38% do pipeline Q3 em stall por mais de 30 dias.
⚡ *Ações / Pendências:*
• Confirmar disponibilidade para ao menos 2 calls executivas com clientes esta semana
📊 *Dados:* Pipeline Q3 = R$ 8,5M · Em risco: R$ 3,2M (38%) · Stall >30 dias em 5 deals

---
*Juliana – Jurídico*
📌 *Assunto Principal:* Processo trabalhista em conciliação — decisão de acordo necessária até amanhã.
⚡ *Ações / Pendências:*
• Decidir sobre aceite do acordo de R$ 85.000 até 09/08 (amanhã)
📊 *Dados:* Proposta de acordo R$ 85.000 · Risco de condenação até R$ 320.000 · Deadline 09/08

---
*Grupo – Board Semanal*
📌 *Assunto Principal:* Reunião do Board antecipada para segunda-feira 11/08 às 09h.
⚡ *Ações / Pendências:*
• Confirmar presença na reunião do Board (11/08, 09h)
📊 *Dados:* Pauta: budget Q4 + filial Porto Alegre CAPEX R$ 1,2M

---
🚨 *AÇÕES IMEDIATAS PRIORITÁRIAS*
• 🔴 **Hoje até 14h** — Aprovar deploy do hotfix de segurança (Rodrigo)
• 🔴 **Até amanhã 09/08** — Decidir sobre acordo trabalhista R$ 85k vs. risco R$ 320k (Juliana)
• 🟠 **Até 10/08** — Assinar 3 ofertas de emprego no sistema RH (Fernanda)
• 🟠 **Até 11/08** — Aprovar realocação R$ 180k de budget de mídia (Ana Paula)
• 🟡 **Até 11/08** — Confirmar presença no Board e revisar pauta (budget Q4 + Porto Alegre)"""


def generate_summary(messages: list[RawMessage], mock: bool = False) -> str:
    """Call the configured LLM and return the executive summary string."""
    if mock:
        return _MOCK_SUMMARY
    user_prompt = build_user_prompt(messages)
    if LLM_PROVIDER == "gemini":
        return _call_gemini(user_prompt, LLM_MODEL)
    return _call_anthropic(user_prompt, LLM_MODEL)


# ---------------------------------------------------------------------------
# n8n POST
# ---------------------------------------------------------------------------

def build_n8n_payload(
    summary: str,
    messages: list[RawMessage],
    webhook_url: str,
) -> dict:
    """Build the JSON body sent to the n8n Webhook node."""
    senders = sorted({m.sender for m in messages})
    return {
        "event": "whatsapp_executive_summary",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_messages_processed": len(messages),
            "unique_senders": len(senders),
            "senders": senders,
        },
        "summary_markdown": summary,
        "metadata": {
            "llm_provider": LLM_PROVIDER,
            "llm_model": LLM_MODEL or (
                DEFAULT_ANTHROPIC_MODEL if LLM_PROVIDER == "anthropic" else DEFAULT_GEMINI_MODEL
            ),
            "webhook_url": webhook_url,
        },
    }


def post_to_n8n(payload: dict, webhook_url: str, api_key: str) -> dict:
    """POST the summary payload to the n8n Webhook URL."""
    headers: dict[str, str] = {"content-type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key  # matches n8n Header Auth credential

    max_attempts = 4
    backoff_seconds = [2, 4, 8, 16]

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(webhook_url, json=payload, headers=headers)
                resp.raise_for_status()
            print(f"[n8n] ✅ POST OK ({resp.status_code}) — attempt {attempt}")
            try:
                return resp.json()
            except Exception:
                return {"status": "ok", "raw": resp.text}
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt < max_attempts:
                wait = backoff_seconds[attempt - 1]
                print(f"[n8n] ⚠️  Attempt {attempt} failed: {exc}. Retrying in {wait}s…", file=sys.stderr)
                time.sleep(wait)

    raise RuntimeError(f"n8n POST failed after {max_attempts} attempts: {last_error}") from last_error


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="WhatsApp → Executive Summary → n8n")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--input", "-i", metavar="FILE", help="JSON file with raw messages array")
    src.add_argument("--stdin", action="store_true", help="Read JSON from stdin")
    p.add_argument("--webhook", "-w", metavar="URL", help="n8n Webhook URL (overrides env)")
    p.add_argument("--dry-run", action="store_true", help="Generate summary but do NOT call n8n")
    p.add_argument("--mock-llm", action="store_true", help="Use built-in mock summary (no API key needed — for testing)")
    p.add_argument("--output-json", metavar="FILE", help="Write n8n payload to a JSON file instead of (or in addition to) posting")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # --- resolve webhook URL ---
    webhook_url = args.webhook or N8N_WEBHOOK_URL
    if not args.dry_run and not webhook_url:
        sys.exit("❌  N8N_WEBHOOK_URL is not set. Pass --webhook or export the env var.")

    # --- load messages ---
    if args.stdin or not args.input:
        raw_json = sys.stdin.read()
    else:
        with open(args.input, encoding="utf-8") as fh:
            raw_json = fh.read()

    try:
        raw_data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        sys.exit(f"❌  Invalid JSON input: {exc}")

    print(f"[load]    Parsing {len(raw_data) if isinstance(raw_data, list) else '?'} raw messages…")
    messages = load_messages(raw_data)
    print(f"[filter]  {len(messages)} messages remain after noise removal.")

    if not messages:
        print("ℹ️  No substantive messages found. Nothing to summarise.")
        sys.exit(0)

    # --- generate summary ---
    if args.mock_llm:
        print("[llm]     Using built-in mock summary (--mock-llm).")
    else:
        print(f"[llm]     Calling {LLM_PROVIDER.upper()} ({LLM_MODEL or 'default model'})…")
    summary = generate_summary(messages, mock=args.mock_llm)
    print("\n" + "─" * 60)
    print(summary)
    print("─" * 60 + "\n")

    # --- build payload ---
    payload = build_n8n_payload(summary, messages, webhook_url)

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"[output]  Payload written to {args.output_json}")

    # --- POST to n8n ---
    if args.dry_run:
        print("[dry-run] Skipping n8n POST. Payload preview:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        result = post_to_n8n(payload, webhook_url, N8N_API_KEY)
        print(f"[n8n]     Response: {json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
