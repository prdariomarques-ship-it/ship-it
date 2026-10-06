"""Daily market briefing — port of the real-data half of FlowCore's
runtime/market_intelligence/briefing.py::build_briefing(). Curve, FX,
equities and commodities, all real Yahoo Finance data, deterministic text.

Deliberately NOT ported (see the user-facing scope decision): the macro
REGIME classification and active ALERTAS sections, which depend on
FlowCore's event-sourced EventRepository/MacroScoreEngine — a subsystem
that doesn't exist in DarioOS. News headlines are also not yet ported:
the original uses yfinance's undocumented `Ticker.news` scraping, which
couldn't be verified live from this environment (Yahoo Finance is
blocked by the sandbox's egress policy) — a future addition once that's
confirmed against the real deployment.
"""
from dataclasses import dataclass, field

from investments.market_tickers import CLASS_LABELS, CURVE_SOURCES, TICKERS
from investments.yahoo_finance import fetch_many_daily_closes, latest_and_delta_pct


@dataclass
class Quote:
    source: str
    category: str
    symbol: str
    unit: str
    value: float
    previous_close: float | None
    delta: float | None  # delta_pct for "price" unit, delta_bps for "pct" unit


@dataclass
class YieldCurveSummary:
    points: dict[str, float]  # source -> yield_pct, only sources with data
    slope_10y_2y_bps: float | None
    state: str
    shape: str | None
    interpretation: str | None


@dataclass
class BriefingSnapshot:
    quotes: dict[str, Quote] = field(default_factory=dict)
    curve: YieldCurveSummary | None = None


async def fetch_briefing_snapshot() -> BriefingSnapshot:
    tickers = [t.symbol for t in TICKERS]
    closes_by_ticker = await fetch_many_daily_closes(tickers)

    quotes: dict[str, Quote] = {}
    for spec in TICKERS:
        closes = closes_by_ticker.get(spec.symbol)
        if not closes:
            continue
        value, delta_pct = latest_and_delta_pct(closes)
        previous_close = closes[-2] if len(closes) >= 2 else None
        delta = delta_pct * 100 if (spec.unit == "pct" and delta_pct is not None) else delta_pct
        quotes[spec.source] = Quote(
            source=spec.source, category=spec.category, symbol=spec.symbol,
            unit=spec.unit, value=value, previous_close=previous_close, delta=delta,
        )

    return BriefingSnapshot(quotes=quotes, curve=_build_curve(quotes))


def _build_curve(quotes: dict[str, Quote]) -> YieldCurveSummary:
    points = {src: q.value for src, _label in CURVE_SOURCES if (q := quotes.get(src)) is not None}
    if len(points) < 2:
        return YieldCurveSummary(points=points, slope_10y_2y_bps=None, state="insufficient_data", shape=None, interpretation=None)

    slope_10y_2y = (
        round((points["treasury"] - points["treasury_2y"]) * 100, 1)
        if "treasury" in points and "treasury_2y" in points else None
    )

    prev = {
        src: q.previous_close
        for src, _label in CURVE_SOURCES
        if (q := quotes.get(src)) is not None and q.previous_close is not None
    }
    prev_slope = (
        round((prev["treasury"] - prev["treasury_2y"]) * 100, 1)
        if "treasury" in prev and "treasury_2y" in prev else None
    )

    state = _classify_state(slope_10y_2y, prev_slope)
    shape, interpretation = _classify_shape(points, prev)
    return YieldCurveSummary(
        points=points, slope_10y_2y_bps=slope_10y_2y, state=state, shape=shape, interpretation=interpretation
    )


def _classify_state(slope_bps: float | None, prev_bps: float | None) -> str:
    if slope_bps is None:
        return "insufficient_data"
    if slope_bps <= 0:
        return "inverted"
    if prev_bps is None:
        return "normal" if slope_bps > 100 else "flat"
    delta = slope_bps - prev_bps
    if delta > 10:
        return "steepening"
    if delta < -10:
        return "flattening"
    return "normal" if slope_bps > 100 else "flat"


def _classify_shape(points: dict[str, float], prev: dict[str, float]) -> tuple[str | None, str | None]:
    """Bull/bear steepening|flattening — only classifies when both the level
    move (long-end average) and the slope move (10Y-2Y spread change) exceed
    5 bps; below that there's no evidence to support a conclusion."""
    if len(prev) < 2:
        return None, None

    delta = {src: (points[src] - prev[src]) * 100 for src in points if src in prev}
    if len(delta) < 2:
        return None, None

    longs = [v for src, v in delta.items() if src in ("treasury", "treasury_30y")]
    short = delta.get("treasury_2y")
    if not longs or short is None:
        return None, None

    level_move = sum(longs) / len(longs)
    slope_move = delta.get("treasury", 0.0) - short

    if abs(level_move) < 5 and abs(slope_move) < 5:
        return None, None

    if slope_move > 5:
        if level_move > 5:
            return "bear_steepening", (
                "A curva americana apresenta bear steepening: yields longos subindo mais "
                "que os curtos, compatível com prêmio de prazo e/ou pressão fiscal."
            )
        if level_move < -5:
            return "bull_steepening", (
                "A curva americana apresenta bull steepening: corte esperado de juros puxa "
                "os curtos para baixo mais que os longos, sinal típico de início de ciclo de "
                "afrouxamento."
            )
        return "steepening", (
            "A curva americana está alongando (steepening) sem movimento direcional claro "
            "de nível — rotacionando de curto para longo."
        )
    if slope_move < -5:
        if level_move > 5:
            return "bear_flattening", (
                "A curva americana apresenta bear flattening: os yields curtos sobem mais "
                "que os longos, pressão de inflação/juros curtos contra expectativa de "
                "desaceleração."
            )
        if level_move < -5:
            return "bull_flattening", (
                "A curva americana apresenta bull flattening: queda generalizada de yields "
                "com longos caindo mais, movimento de busca de segurança (flight to quality)."
            )
        return "flattening", (
            "A curva americana está achando (flattening) sem movimento direcional claro de "
            "nível — expectativas de política monetária convergindo no médio prazo."
        )
    return None, None


def format_briefing_message(snapshot: BriefingSnapshot) -> str:
    lines = ["🇧🇷 *DARIO OS — RADAR DE MERCADO*", ""]

    curve = snapshot.curve
    if curve and curve.state != "insufficient_data":
        slope_txt = f" (10Y-2Y {curve.slope_10y_2y_bps} bps)" if curve.slope_10y_2y_bps is not None else ""
        lines.append(f"CURVA EUA: {curve.state}{slope_txt}")
        if curve.interpretation:
            lines.append(f"  {curve.interpretation}")
        for source, label in CURVE_SOURCES:
            if source in curve.points:
                lines.append(f"  {label}: {curve.points[source]:.2f}%")

    dollar = snapshot.quotes.get("dollar")
    dxy = snapshot.quotes.get("dxy")
    if dxy:
        lines.append(f"DÓLAR: DXY {_fmt(dxy.delta)}% no dia")
    for source in ("dollar", "dxy", "eurusd", "usd_jpy", "usdcny"):
        q = snapshot.quotes.get(source)
        if q:
            lines.append(f"  {source.upper()}: {q.value:.4f} ({_fmt(q.delta)}%)")

    by_category: dict[str, list] = {}
    for q in snapshot.quotes.values():
        by_category.setdefault(q.category, []).append(q)
    for category in ("equities", "commodities", "volatility"):
        sources = by_category.get(category, [])
        if not sources:
            continue
        movers = [q for q in sources if q.delta is not None and abs(q.delta) >= 1]
        label = CLASS_LABELS.get(category, category).upper()
        if movers:
            highlights = ", ".join(f"{q.source} {q.delta:+.1f}%" for q in movers)
            lines.append(f"{label}: {len(sources)} fontes | destaques: {highlights}")
        else:
            lines.append(f"{label}: {len(sources)} fontes")

    return "\n".join(lines)[:4095]


def _fmt(v: float | None) -> str:
    return f"{v:+.2f}" if v is not None else "—"
