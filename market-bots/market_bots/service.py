"""Application layer: builds bulletins, on-demand answers and alerts from ports. No HTTP, no Telegram here."""
from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from . import formatting as fmt
from .domain import Filing, FilingsSpec, Instrument, Profile, ProviderError, Quote, Result, Section
from .ports import QuoteProvider, StateStore
from .providers.yahoo import SYMBOL as YAHOO_SYMBOL

log = logging.getLogger("market_bots.service")


@dataclass(frozen=True)
class PendingAlert:
    key: str    # state key to set once the alert was delivered
    text: str


class FilingSource(Protocol):
    def recent(self, spec: FilingsSpec, now: datetime) -> list[Filing]: ...


class MarketService:
    def __init__(self, provider: QuoteProvider, filings: FilingSource | None, tz: ZoneInfo,
                 now: Callable[[], datetime], workers: int = 8) -> None:
        self._provider = provider
        self._filings = filings
        self._tz = tz
        self._now = now
        self._workers = workers

    # ---- fetching -----------------------------------------------------------------------------------------
    def _one(self, instrument: Instrument) -> Result:
        try:
            return Result(instrument=instrument, quote=self._provider.fetch(instrument))
        except ProviderError as exc:
            return Result(instrument=instrument, error=str(exc))
        except Exception:  # noqa: BLE001 - one bad instrument must never take the bulletin down
            log.exception("unexpected provider failure for %s", instrument.symbol)
            return Result(instrument=instrument, error="falha inesperada")

    def fetch_many(self, instruments: tuple[Instrument, ...] | list[Instrument]) -> list[Result]:
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            return list(pool.map(self._one, instruments))   # map preserves order

    # ---- blocks -------------------------------------------------------------------------------------------
    def section_message(self, section: Section, now: datetime | None = None) -> str:
        now = now or self._now()
        return fmt.section_block(section, self.fetch_many(section.instruments), self._tz, now)

    def movers_message(self, profile: Profile, now: datetime | None = None) -> str | None:
        spec = profile.movers
        if spec is None:
            return None
        now = now or self._now()
        results = self.fetch_many(spec.universe)
        ok = [r for r in results if r.quote is not None and r.quote.change_pct is not None]
        ups = sorted((r for r in ok if r.quote.change_pct > 0), key=lambda r: r.quote.change_pct, reverse=True)[: spec.top_n]  # type: ignore[union-attr]
        downs = sorted((r for r in ok if r.quote.change_pct < 0), key=lambda r: r.quote.change_pct)[: spec.top_n]  # type: ignore[union-attr]
        failed = sum(1 for r in results if r.quote is None)
        return fmt.movers_block(spec.title, ups, downs, failed, len(results), self._tz, now)

    def filings_message(self, profile: Profile, now: datetime | None = None) -> str | None:
        spec = profile.filings
        if spec is None or self._filings is None:
            return None
        now = now or self._now()
        try:
            items = self._filings.recent(spec, now)
        except ProviderError as exc:
            return fmt.filings_block([], 0, self._tz, error=str(exc))
        return fmt.filings_block(items[: spec.max_items], len(items), self._tz)

    def bulletin(self, profile: Profile, now: datetime | None = None) -> list[str]:
        now = now or self._now()
        blocks = [fmt.header(profile.title, self._tz, now)]
        blocks.extend(self.section_message(s, now) for s in profile.sections)
        for extra in (self.movers_message(profile, now), self.filings_message(profile, now)):
            if extra:
                blocks.append(extra)
        return fmt.join_blocks(blocks)

    def quote_message(self, symbol: str) -> str:
        """On-demand /cotacao for any Yahoo symbol. The symbol is validated: it ends up in a URL."""
        symbol = symbol.strip().upper()
        if not YAHOO_SYMBOL.match(symbol):
            return "Símbolo inválido. Exemplo: /cotacao PETR4.SA"
        result = self._one(Instrument(kind="yahoo", symbol=symbol, name=symbol, decimals=2))
        return fmt.quote_line(result, self._tz, self._now())

    # ---- alerts -------------------------------------------------------------------------------------------
    def alerts(self, profile: Profile, state: StateStore, now: datetime | None = None) -> list[PendingAlert]:
        """Alerts not reported yet. NOTHING is marked as reported here: the caller commits each one only after it was
        delivered, so a failed delivery is retried on the next pass instead of being lost."""
        now = now or self._now()
        day = now.astimezone(self._tz).date().isoformat()
        out: list[PendingAlert] = []
        by_symbol = {i.symbol: i for s in profile.sections for i in s.instruments}
        rules = [r for r in profile.alerts if r.symbol in by_symbol]
        for rule, result in zip(rules, self.fetch_many([by_symbol[r.symbol] for r in rules]), strict=True):
            q: Quote | None = result.quote
            if q is None or q.change_pct is None or abs(q.change_pct) < rule.min_abs_change_pct:
                continue
            direction = "up" if q.change_pct > 0 else "down"
            key = f"alert:{profile.id}:{rule.symbol}:{day}:{direction}"
            if state.get(key):
                continue
            label = rule.label or result.instrument.name
            out.append(PendingAlert(
                key=key,
                text=f"ALERTA - {label}: {fmt.pct(q.change_pct)} (limite ±{fmt.num(rule.min_abs_change_pct, 1)}%) "
                     f"em {fmt.num(q.value, result.instrument.decimals)}",
            ))
        out.extend(self._new_filings(profile, state, now))
        return out

    def _new_filings(self, profile: Profile, state: StateStore, now: datetime) -> list[PendingAlert]:
        spec = profile.filings
        if spec is None or self._filings is None:
            return []
        try:
            items = self._filings.recent(spec, now)
        except ProviderError as exc:
            log.warning("filings unavailable for alerts: %s", exc)
            return []
        fresh = [f for f in items if state.get(f"filing:{profile.id}:{f.key}") is None]
        seeded_key = f"filings_seeded:{profile.id}"
        if state.get(seeded_key) is None:
            # Baseline only: announcing the whole backlog on the first boot would be noise, not an alert.
            for f in fresh:
                state.set(f"filing:{profile.id}:{f.key}", now.isoformat())
            state.set(seeded_key, now.isoformat())
            return []
        return [
            PendingAlert(
                key=f"filing:{profile.id}:{f.key}",
                text=f"NOVO {f.category.upper()} - {f.company}: {f.subject or '(sem assunto)'}" + (f"\n{f.link}" if f.link else ""),
            )
            for f in fresh
        ]