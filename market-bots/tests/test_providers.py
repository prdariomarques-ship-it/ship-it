"""Providers against response shapes captured from the real sources on 2026-10-19 (no network in tests)."""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone

import pytest

from market_bots.domain import FilingsSpec, Instrument, ProviderError
from market_bots.providers import RoutingProvider
from market_bots.providers.awesomeapi import AwesomeApiFx
from market_bots.providers.bcb import BcbSgs
from market_bots.providers.cvm import CvmIpe
from market_bots.providers.focus import BcbFocus
from market_bots.providers.gold import GoldBrlPerGram
from market_bots.providers.yahoo import YahooProvider

from .conftest import FakeProvider, utc


def yahoo_body(price=205079.25, when=1792441080, closes=(206888.0, 206506.0, 204324.0, 205430.0, 205079.25)):
    return {"chart": {"result": [{"meta": {"regularMarketPrice": price, "regularMarketTime": when},
                                  "timestamp": list(range(len(closes))), "indicators": {"quote": [{"close": list(closes)}]}}],
                      "error": None}}


IBOV = Instrument("yahoo", "^BVSP", "Ibovespa")


def test_yahoo_change_is_vs_previous_session_not_the_5d_window():
    q = YahooProvider(lambda url: yahoo_body()).fetch(IBOV)
    assert q.value == 205079.25
    assert q.change_pct == pytest.approx((205079.25 / 205430.0 - 1) * 100)      # vs closes[-2]
    assert q.as_of == datetime.fromtimestamp(1792441080, tz=timezone.utc)


def test_yahoo_skips_null_closes_and_omits_change_when_unknown():
    q = YahooProvider(lambda u: yahoo_body(closes=(None, 100.0, None, 110.0))).fetch(IBOV)
    assert q.change_pct == pytest.approx((205079.25 / 100.0 - 1) * 100)
    assert YahooProvider(lambda u: yahoo_body(closes=(100.0,))).fetch(IBOV).change_pct is None   # never 0


@pytest.mark.parametrize("body", [{}, {"chart": {"result": None, "error": {"description": "No data found"}}},
                                  yahoo_body(price=None)])
def test_yahoo_bad_bodies_raise_provider_error(body):
    with pytest.raises(ProviderError):
        YahooProvider(lambda u: body).fetch(IBOV)


@pytest.mark.parametrize("sym", ["", "A B", "X;rm", "../etc", "A" * 21, "PETR4.SA?x=1"])
def test_yahoo_rejects_symbols_that_could_alter_the_url(sym):
    calls = []
    with pytest.raises(ProviderError):
        YahooProvider(lambda u: calls.append(u)).fetch(Instrument("yahoo", sym, "x"))
    assert calls == []


def test_yahoo_url_is_fixed_host_and_escaped():
    seen = []
    YahooProvider(lambda u: (seen.append(u), yahoo_body())[1]).fetch(IBOV)
    assert seen[0].startswith("https://query1.finance.yahoo.com/v8/finance/chart/%5EBVSP?")


def test_awesomeapi_real_shape():
    body = {"USDBRL": {"bid": "5.0402", "pctChange": "-0.479808", "timestamp": "1792449006"}}
    q = AwesomeApiFx(lambda u: body).fetch(Instrument("fx", "USD-BRL", "Dólar"))
    assert q.value == 5.0402 and q.change_pct == pytest.approx(-0.479808)
    with pytest.raises(ProviderError):
        AwesomeApiFx(lambda u: {}).fetch(Instrument("fx", "USD-BRL", "Dólar"))
    with pytest.raises(ProviderError):
        AwesomeApiFx(lambda u: body).fetch(Instrument("fx", "usd;brl", "x"))


def test_bcb_sgs_real_shape_and_no_change():
    q = BcbSgs(lambda u: [{"data": "16/10/2026", "valor": "13.65"}]).fetch(Instrument("sgs", "4389", "CDI"))
    assert q.value == 13.65 and q.change_pct is None and q.as_of == utc(2026, 10, 16, 12)
    with pytest.raises(ProviderError):
        BcbSgs(lambda u: []).fetch(Instrument("sgs", "4389", "CDI"))
    with pytest.raises(ProviderError):
        BcbSgs(lambda u: []).fetch(Instrument("sgs", "4389/../x", "CDI"))


def test_focus_real_shape_and_symbol_whitelist():
    body = {"value": [{"Indicador": "Selic", "Data": "2026-10-16", "DataReferencia": "2026", "Mediana": 13.25}]}
    urls = []
    q = BcbFocus(lambda u: (urls.append(u), body)[1]).fetch(Instrument("focus", "Selic:2026", "Focus"))
    assert q.value == 13.25 and q.as_of == utc(2026, 10, 16, 12)
    assert "Selic" in urls[0] and "%27" in urls[0]          # filter is percent-encoded
    with pytest.raises(ProviderError):
        BcbFocus(lambda u: body).fetch(Instrument("focus", "Selic' or 1 eq 1:2026", "x"))
    with pytest.raises(ProviderError):
        BcbFocus(lambda u: {"value": []}).fetch(Instrument("focus", "Selic:2026", "x"))


def test_gold_in_reais_per_gram_is_derived_and_needs_both_legs():
    ounce = 31.1034768
    prov = FakeProvider({"GC=F": (4155.1, 1.0), "USD-BRL": (5.0402, -0.5)}, utc(2026, 10, 19, 22))
    q = GoldBrlPerGram(prov, prov).fetch(Instrument("gold_brl", "", "Ouro"))
    assert q.value == pytest.approx(4155.1 * 5.0402 / ounce)
    assert q.change_pct == pytest.approx((1.01 * 0.995 - 1) * 100)
    broken = FakeProvider({"GC=F": (4155.1, 1.0)}, utc(2026, 10, 19, 22))
    with pytest.raises(ProviderError):
        GoldBrlPerGram(broken, broken).fetch(Instrument("gold_brl", "", "Ouro"))


def test_routing_provider_dispatches_by_kind_and_rejects_unknown():
    fake = FakeProvider({"X": (1.0, 0.1)}, utc(2026, 10, 19))
    r = RoutingProvider({"yahoo": fake})
    assert r.fetch(Instrument("yahoo", "X", "x")).value == 1.0
    with pytest.raises(ProviderError):
        r.fetch(Instrument("fx", "USD-BRL", "x"))


def cvm_zip(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    cols = ["CNPJ_Companhia", "Nome_Companhia", "Codigo_CVM", "Data_Referencia", "Categoria", "Tipo", "Especie", "Assunto",
            "Data_Entrega", "Tipo_Apresentacao", "Protocolo_Entrega", "Versao", "Link_Download"]
    w = csv.DictWriter(buf, fieldnames=cols, delimiter=";")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in cols})
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("ipe_cia_aberta_2026.csv", buf.getvalue().encode("latin-1"))
    return out.getvalue()


def test_cvm_filters_by_category_company_and_window_and_sorts_newest_first():
    rows = [
        {"Nome_Companhia": "PETROLEO BRASILEIRO S.A. - PETROBRAS", "Categoria": "Fato Relevante", "Assunto": "Dividendos",
         "Data_Entrega": "2026-10-19", "Protocolo_Entrega": "P1", "Link_Download": "https://x/1"},
        {"Nome_Companhia": "VALE S.A.", "Categoria": "Fato Relevante", "Assunto": "Operação",
         "Data_Entrega": "2026-10-18 09:00:00", "Protocolo_Entrega": "P2"},
        {"Nome_Companhia": "VALE S.A.", "Categoria": "Comunicado ao Mercado", "Assunto": "x",
         "Data_Entrega": "2026-10-19", "Protocolo_Entrega": "P3"},
        {"Nome_Companhia": "OUTRA S.A.", "Categoria": "Fato Relevante", "Assunto": "y",
         "Data_Entrega": "2026-10-19", "Protocolo_Entrega": "P4"},
        {"Nome_Companhia": "PETROLEO BRASILEIRO S.A. - PETROBRAS", "Categoria": "Fato Relevante", "Assunto": "velho",
         "Data_Entrega": "2026-09-01", "Protocolo_Entrega": "P5"},
        {"Nome_Companhia": "VALE S.A.", "Categoria": "Fato Relevante", "Assunto": "sem protocolo",
         "Data_Entrega": "2026-10-19", "Protocolo_Entrega": ""},
    ]
    fetched = []
    src = CvmIpe(lambda url: (fetched.append(url), cvm_zip(rows))[1])
    now = utc(2026, 10, 19, 15)
    got = src.recent(FilingsSpec(companies=("petrobras", "vale s.a"), window_hours=48), now)
    assert [f.key for f in got] == ["P1", "P2"]
    assert fetched == ["https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_2026.zip"]
    everyone = src.recent(FilingsSpec(companies=(), window_hours=48), now)
    assert {f.key for f in everyone} == {"P1", "P2", "P4"}
    assert len(fetched) == 1                                   # cached: a second pass does not re-download


def test_cvm_failures_surface_as_provider_error():
    def boom(url):
        raise ProviderError("source unreachable")

    with pytest.raises(ProviderError):
        CvmIpe(boom).recent(FilingsSpec(), utc(2026, 10, 19))
    with pytest.raises(ProviderError):
        CvmIpe(lambda u: b"not a zip").recent(FilingsSpec(), utc(2026, 10, 19))
