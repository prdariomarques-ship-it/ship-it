"""B3/Ibovespa + USD/BRL summary — the PMX (@dariozcodebot) feed, real data only.

Ports runtime/telegram.py::build_b3_summary_message() from the original
FlowCore (Python/FastAPI) repo into DarioOS, same tickers, same two data
points, now delivered over Telegram instead of a dedicated bot.
"""
from dataclasses import dataclass

from investments.yahoo_finance import age_disclosure, fetch_price_series, latest_and_delta_pct

IBOVESPA_TICKER = "^BVSP"
USDBRL_TICKER = "USDBRL=X"


@dataclass
class B3Summary:
    ibovespa_points: float
    ibovespa_delta_pct: float | None
    usdbrl_level: float
    usdbrl_delta_pct: float | None
    max_age_hours: float  # older of the two tickers' quote ages — see age_disclosure


def _fmt_index_value(value: float) -> str:
    """166934.2 -> '166.934' (Brazilian thousands separator, no decimals)."""
    return f"{round(value):,}".replace(",", ".")


def _fmt_delta_pct(delta: float | None) -> str:
    if delta is None:
        return "sem variação disponível"
    return f"{delta:+.2f}%"


async def check_b3_summary() -> B3Summary:
    ibov_series = await fetch_price_series(IBOVESPA_TICKER, range_="5d")
    usdbrl_series = await fetch_price_series(USDBRL_TICKER, range_="5d")
    ibov_value, ibov_delta = latest_and_delta_pct(ibov_series.closes)
    usdbrl_value, usdbrl_delta = latest_and_delta_pct(usdbrl_series.closes)
    return B3Summary(
        ibovespa_points=ibov_value,
        ibovespa_delta_pct=ibov_delta,
        usdbrl_level=usdbrl_value,
        usdbrl_delta_pct=usdbrl_delta,
        max_age_hours=max(ibov_series.age_seconds(), usdbrl_series.age_seconds()) / 3600,
    )


def format_b3_summary_message(summary: B3Summary) -> str:
    lines = [
        "🇧🇷 <b>DARIO OS — RADAR B3</b>",
        "",
        f"📊 <b>IBOVESPA</b>: {_fmt_index_value(summary.ibovespa_points)} pts "
        f"({_fmt_delta_pct(summary.ibovespa_delta_pct)})",
        f"💵 <b>USD/BRL</b>: R$ {summary.usdbrl_level:.4f} ({_fmt_delta_pct(summary.usdbrl_delta_pct)})",
    ]
    age_line = age_disclosure(summary.max_age_hours)
    if age_line:
        lines.append(age_line)
    return "\n".join(lines)
