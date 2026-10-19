"""BCB Focus survey (annual market expectations, median). Symbol: 'Indicador:Ano', e.g. 'Selic:2026', 'IPCA:2027'."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote

from ..domain import Instrument, ProviderError, Quote
from .http import JsonFetcher, fetch_json

_SYMBOL = re.compile(r"^(IPCA|Selic|Câmbio|PIB Total|IGP-M):(20\d\d)$")
_BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais"


class BcbFocus:
    def __init__(self, fetch: JsonFetcher = fetch_json) -> None:
        self._fetch = fetch

    def fetch(self, instrument: Instrument) -> Quote:
        m = _SYMBOL.match(instrument.symbol)
        if not m:
            raise ProviderError("invalid Focus symbol")
        indicator, year = m.groups()
        flt = f"Indicador eq '{indicator}' and DataReferencia eq '{year}' and baseCalculo eq 0"
        url = f"{_BASE}?$top=1&$orderby=Data%20desc&$format=json&$filter={quote(flt, safe='')}"
        body = self._fetch(url)
        try:
            row = body["value"][0]  # type: ignore[index]
            value = float(row["Mediana"])
            as_of = datetime.strptime(row["Data"], "%Y-%m-%d").replace(hour=12, tzinfo=timezone.utc)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("no Focus data for this indicator/year") from exc
        return Quote(instrument=instrument, value=value, as_of=as_of, change_pct=None)
