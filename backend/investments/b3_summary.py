"""B3/Ibovespa + USD/BRL summary — the PMX (@dariozcodebot) feed, real data only.

Ports runtime/telegram.py::build_b3_summary_message() from the original
FlowCore (Python/FastAPI) repo into DarioOS, same tickers, same two data
points, now delivered over WhatsApp instead of a dedicated Telegram bot.
"""
from dataclasses import dataclass

from investments.yahoo_finance import fetch_daily_closes, latest_and_delta_pct

IBOVESPA_TICKER = "^BVSP"
USDBRL_TICKER = "USDBRL=X"


@dataclass
class B3Summary:
    ibovespa_points: float
    ibovespa_delta_pct: float | None
    usdbrl_level: float
    usdbrl_delta_pct: float | None


def _fmt_index_value(value: float) -> str:
    """166934.2 -> '166.934' (Brazilian thousands separator, no decimals)."""
    return f"{round(value):,}".replace(",", ".")


def _fmt_delta_pct(delta: float | None) -> str:
    if delta is None:
        return "sem variação disponível"
    return f"{delta:+.2f}%"


async def check_b3_summary() -> B3Summary:
    ibov_closes = await fetch_daily_closes(IBOVESPA_TICKER, range_="5d")
    usdbrl_closes = await fetch_daily_closes(USDBRL_TICKER, range_="5d")
    ibov_value, ibov_delta = latest_and_delta_pct(ibov_closes)
    usdbrl_value, usdbrl_delta = latest_and_delta_pct(usdbrl_closes)
    return B3Summary(
        ibovespa_points=ibov_value,
        ibovespa_delta_pct=ibov_delta,
        usdbrl_level=usdbrl_value,
        usdbrl_delta_pct=usdbrl_delta,
    )


def format_b3_summary_message(summary: B3Summary) -> str:
    lines = [
        "🇧🇷 *DARIO OS — RADAR B3*",
        "",
        f"📊 *IBOVESPA*: {_fmt_index_value(summary.ibovespa_points)} pts "
        f"({_fmt_delta_pct(summary.ibovespa_delta_pct)})",
        f"💵 *USD/BRL*: R$ {summary.usdbrl_level:.4f} ({_fmt_delta_pct(summary.usdbrl_delta_pct)})",
    ]
    return "\n".join(lines)
