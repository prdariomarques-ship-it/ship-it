"""Plain-text pt-BR rendering for Telegram. No parse_mode: nothing to escape, nothing to inject.

Honesty rules (enforced by tests): a failed instrument is shown as unavailable - never as a number; a quote whose
source date is not today carries that date; a missing change is omitted - never rendered as 0,00%.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .domain import Filing, Result, Section

TELEGRAM_LIMIT = 4096
_SAFE = 3900   # leave room for a truncation footer


def num(value: float, decimals: int = 2) -> str:
    s = f"{value:,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(value: float) -> str:
    value = round(value, 2) + 0.0          # -0.004 -> 0.0: never "-0,00%" or "▲ +0,00%"
    if value == 0:
        return "■ 0,00%"
    arrow = "▲" if value > 0 else "▼"
    return f"{arrow} {value:+.2f}%".replace(".", ",")


def quote_line(result: Result, tz: ZoneInfo, today: datetime) -> str:
    ins = result.instrument
    if result.quote is None:
        return f"• {ins.name}: indisponível ({result.error or 'sem dados'})"
    q = result.quote
    unit = f" {ins.unit}" if ins.unit else ""
    parts = [f"• {ins.name}: {num(q.value, ins.decimals)}{unit}"]
    if q.change_pct is not None:
        parts.append(pct(q.change_pct))
    local = q.as_of.astimezone(tz)
    if ins.unit.endswith("a.m."):
        parts.append(f"(ref. {local:%m/%Y})")      # monthly series: the reference month, not a misleading day
    elif local.date() != today.astimezone(tz).date():
        parts.append(f"({local:%d/%m})")
    return "  ".join(parts)


def section_block(section: Section, results: list[Result], tz: ZoneInfo, now: datetime) -> str:
    head = section.title.upper()
    lines = [head]
    if section.note:
        lines.append(f"ℹ {section.note}")
    lines.extend(quote_line(r, tz, now) for r in results)
    return "\n".join(lines)


def movers_block(title: str, ups: list[Result], downs: list[Result], failed: int, total: int,
                 tz: ZoneInfo, now: datetime) -> str:
    lines = [title.upper()]
    if not ups and not downs:
        lines.append(f"indisponível ({failed}/{total} cotações falharam)")
        return "\n".join(lines)
    lines.append("Altas")
    lines.extend(_mover_line(r) for r in ups)
    lines.append("Quedas")
    lines.extend(_mover_line(r) for r in downs)
    if failed:
        lines.append(f"ℹ {failed} de {total} papéis sem cotação nesta rodada")
    return "\n".join(lines)


def _mover_line(r: Result) -> str:
    q = r.quote
    assert q is not None and q.change_pct is not None
    return f"• {r.instrument.name}: {num(q.value)}  {pct(q.change_pct)}"


def filings_block(items: list[Filing], total: int, tz: ZoneInfo, error: str | None = None) -> str:
    lines = ["FATOS RELEVANTES (CVM)"]
    if error:
        return "\n".join(lines + [f"indisponível ({error})"])
    if not items:
        return "\n".join(lines + ["nenhum no período"])
    for f in items:
        lines.append(f"• {f.company} - {f.subject or f.category} ({f.delivered_at.astimezone(tz):%d/%m})")
        if f.link:
            lines.append(f"  {f.link}")
    if total > len(items):
        lines.append(f"… e mais {total - len(items)}")
    return "\n".join(lines)


def header(title: str, tz: ZoneInfo, now: datetime) -> str:
    return f"{title} - {now.astimezone(tz):%d/%m/%Y %H:%M}"


def join_blocks(blocks: list[str]) -> list[str]:
    """Join with blank lines and split on block boundaries so no message exceeds Telegram's limit."""
    messages: list[str] = []
    current = ""
    for block in blocks:
        if len(block) > _SAFE:
            block = block[:_SAFE] + "\n… (truncado)"
        if current and len(current) + 2 + len(block) > _SAFE:
            messages.append(current)
            current = block
        else:
            current = f"{current}\n\n{block}" if current else block
    if current:
        messages.append(current)
    return messages
