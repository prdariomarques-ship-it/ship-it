"""Real-data market ticker registry — ports default_yfinance_observers() from
the original FlowCore repo (runtime/observers/market_observers.py), minus
the tickers only used by the macro-regime/alerts subsystems this port skips.
"""
from dataclasses import dataclass


@dataclass
class TickerSpec:
    source: str
    category: str  # "rates" | "fx" | "equities" | "commodities"
    symbol: str
    unit: str  # "pct" (yields, delta in bps) or "price" (delta in %)


CLASS_LABELS = {
    "rates": "Taxas (Treasuries)",
    "fx": "Câmbio",
    "equities": "Bolsas (Equities)",
    "commodities": "Commodities",
    "volatility": "Volatilidade",
}

TICKERS: list[TickerSpec] = [
    TickerSpec(source="treasury", category="rates", symbol="^TNX", unit="pct"),
    TickerSpec(source="treasury_5y", category="rates", symbol="^FVX", unit="pct"),
    TickerSpec(source="treasury_2y", category="rates", symbol="^IRX", unit="pct"),
    TickerSpec(source="treasury_30y", category="rates", symbol="^TYX", unit="pct"),
    TickerSpec(source="dollar", category="fx", symbol="USDBRL=X", unit="price"),
    TickerSpec(source="dxy", category="fx", symbol="DX-Y.NYB", unit="price"),
    TickerSpec(source="eurusd", category="fx", symbol="EURUSD=X", unit="price"),
    TickerSpec(source="usd_jpy", category="fx", symbol="JPY=X", unit="price"),
    TickerSpec(source="usdcny", category="fx", symbol="CNY=X", unit="price"),
    TickerSpec(source="ibovespa", category="equities", symbol="^BVSP", unit="price"),
    TickerSpec(source="sp500", category="equities", symbol="^GSPC", unit="price"),
    TickerSpec(source="nasdaq", category="equities", symbol="^IXIC", unit="price"),
    TickerSpec(source="dow", category="equities", symbol="^DJI", unit="price"),
    TickerSpec(source="russell2000", category="equities", symbol="^RUT", unit="price"),
    TickerSpec(source="eurostoxx", category="equities", symbol="^STOXX50E", unit="price"),
    TickerSpec(source="dax", category="equities", symbol="^GDAXI", unit="price"),
    TickerSpec(source="ftse", category="equities", symbol="^FTSE", unit="price"),
    TickerSpec(source="nikkei", category="equities", symbol="^N225", unit="price"),
    TickerSpec(source="hangseng", category="equities", symbol="^HSI", unit="price"),
    TickerSpec(source="shanghai", category="equities", symbol="000001.SS", unit="price"),
    TickerSpec(source="oil", category="commodities", symbol="BZ=F", unit="price"),
    TickerSpec(source="wti", category="commodities", symbol="CL=F", unit="price"),
    TickerSpec(source="gold", category="commodities", symbol="GC=F", unit="price"),
    TickerSpec(source="silver", category="commodities", symbol="SI=F", unit="price"),
    TickerSpec(source="copper", category="commodities", symbol="HG=F", unit="price"),
    TickerSpec(source="vix", category="volatility", symbol="^VIX", unit="price"),
]

# US Treasury curve, ascending maturity — mirrors yield_curve.py's CURVE_SOURCES.
CURVE_SOURCES = [
    ("treasury_2y", "2Y (IRX ~13wk proxy)"),
    ("treasury_5y", "5Y"),
    ("treasury", "10Y"),
    ("treasury_30y", "30Y"),
]
