"""Banco Central SGS series (no key): Selic meta (432), CDI a.a. (4389), IPCA m/m (433), IGP-M m/m (189)."""
from __future__ import annotations

from datetime import datetime, timezone

from ..domain import Instrument, ProviderError, Quote
from .http import JsonFetcher, fetch_json


class BcbSgs:
    def __init__(self, fetch: JsonFetcher = fetch_json) -> None:
        self._fetch = fetch

    def fetch(self, instrument: Instrument) -> Quote:
        code = instrument.symbol
        if not code.isdigit() or len(code) > 6:
            raise ProviderError("invalid series code")
        body = self._fetch(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados/ultimos/1?formato=json")
        try:
            row = body[-1]  # type: ignore[index]
            value = float(str(row["valor"]).replace(",", "."))
            # The series date is a reference DAY, not an instant: noon UTC keeps that calendar day in any Brazilian zone.
            as_of = datetime.strptime(row["data"], "%d/%m/%Y").replace(hour=12, tzinfo=timezone.utc)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("unexpected response shape") from exc
        return Quote(instrument=instrument, value=value, as_of=as_of, change_pct=None)
