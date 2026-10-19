"""CVM open data, IPE (documents filed by listed companies): Fato Relevante, Comunicado ao Mercado, ...

Source: dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_<year>.zip (a CSV, ';'-separated, latin-1).
The file is refreshed by CVM on its own cadence, so 'recent' means 'already published there', not 'filed this second'.
"""
from __future__ import annotations

import csv
import io
import time
import zipfile
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..domain import Filing, FilingsSpec, ProviderError

BytesFetcher = Callable[[str], bytes]
_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{year}.zip"
MAX_ZIP = 30_000_000


def fetch_bytes(url: str, timeout: float = 30.0) -> bytes:
    if not url.startswith("https://"):
        raise ProviderError("only https sources are allowed")
    req = Request(url, headers={"User-Agent": "market-bots/1.0 (+personal use)"})
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - scheme checked above
            raw = resp.read(MAX_ZIP + 1)
    except HTTPError as exc:
        raise ProviderError(f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ProviderError("source unreachable") from exc
    if len(raw) > MAX_ZIP:
        raise ProviderError("response too large")
    return raw


def _parse_date(value: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


class CvmIpe:
    def __init__(self, fetch: BytesFetcher = fetch_bytes, cache_seconds: int = 600,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self._fetch = fetch
        self._ttl = cache_seconds
        self._mono = monotonic
        self._cache: dict[int, tuple[float, list[Filing]]] = {}

    def _year(self, year: int) -> list[Filing]:
        hit = self._cache.get(year)
        if hit and self._mono() - hit[0] < self._ttl:
            return hit[1]
        raw = self._fetch(_URL.format(year=year))
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
                text = zf.read(name).decode("latin-1")
        except (zipfile.BadZipFile, StopIteration, KeyError) as exc:
            raise ProviderError("unexpected CVM file") from exc
        out: list[Filing] = []
        for row in csv.DictReader(io.StringIO(text), delimiter=";"):
            when = _parse_date(row.get("Data_Entrega", ""))
            key = (row.get("Protocolo_Entrega") or "").strip()
            if when is None or not key:
                continue
            out.append(Filing(
                key=key, company=(row.get("Nome_Companhia") or "").strip(), category=(row.get("Categoria") or "").strip(),
                subject=(row.get("Assunto") or "").strip(), delivered_at=when, link=(row.get("Link_Download") or "").strip(),
            ))
        self._cache[year] = (self._mono(), out)
        return out

    def recent(self, spec: FilingsSpec, now: datetime) -> list[Filing]:
        """Newest first. A year boundary reads both years. Raises ProviderError if the source fails."""
        since = (now - timedelta(hours=spec.window_hours)).replace(hour=0, minute=0, second=0, microsecond=0)
        years = sorted({since.year, now.year})
        rows = [f for y in years for f in self._year(y)]
        wanted = tuple(c.lower() for c in spec.companies)
        cats = {c.lower() for c in spec.categories}
        picked = [
            f for f in rows
            if f.delivered_at >= since and f.category.lower() in cats
            and (not wanted or any(w in f.company.lower() for w in wanted))
        ]
        picked.sort(key=lambda f: (f.delivered_at, f.key), reverse=True)
        return picked
