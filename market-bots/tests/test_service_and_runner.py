from __future__ import annotations

import pytest

from market_bots import formatting as fmt
from market_bots.commands import CommandRouter
from market_bots.domain import (
    AlertRule,
    Filing,
    FilingsSpec,
    Instrument,
    MoversSpec,
    Profile,
    ProviderError,
    Quote,
    Section,
)
from market_bots.runner import BotRunner
from market_bots.service import MarketService
from market_bots.telegram import DeliveryError, PollConflict, TelegramApi, TransportError

from .conftest import TZ, FakeFilings, FakeProvider, local, utc

IBOV = Instrument("yahoo", "^BVSP", "Ibovespa", "pts", 0)
USD = Instrument("fx", "USD-BRL", "Dólar", "R$", 4)
CDI = Instrument("sgs", "4389", "CDI", "% a.a.")
NOW = local(2026, 10, 19, 10, 25)


def profile(**over) -> Profile:
    base = dict(
        id="national", title="Mercado Brasil", token_env="T", chat_env="C", schedule=("10:20", "18:20"),
        weekdays_only=True, catchup_minutes=30,
        sections=(Section("indices", "Bolsa", (IBOV,)), Section("cambio", "Câmbio", (USD, CDI))),
        movers=MoversSpec("Altas e quedas", tuple(Instrument("yahoo", f"T{i}.SA", f"T{i}") for i in range(8)), top_n=2),
        filings=FilingsSpec(), alerts=(AlertRule("^BVSP", 2.0, "Ibovespa"), AlertRule("USD-BRL", 1.5, "Dólar")),
    )
    base.update(over)
    return Profile(**base)


def service(table, filings=None, now=NOW):
    prov = FakeProvider(table, now)
    return MarketService(prov, filings, TZ, lambda: now), prov


TABLE = {"^BVSP": (205079.25, -0.17), "USD-BRL": (5.0402, -0.48), "4389": (13.65, None),
         "T0.SA": (10, 5.0), "T1.SA": (11, 3.0), "T2.SA": (12, 0.5), "T3.SA": (13, -1.0), "T4.SA": (14, -6.0),
         "T5.SA": (15, 0.0), "T6.SA": ProviderError("sem cotação"), "T7.SA": (17, -3.0)}


# ------------------------------------------------------------
def test_numbers_use_brazilian_format():
    assert fmt.num(205079.25, 0) == "205.079" and fmt.num(5.0402, 4) == "5,0402" and fmt.num(1234567.891) == "1.234.567,89"
    assert fmt.pct(-0.48) == "▼ -0,48%" and fmt.pct(1.5) == "▲ +1,50%"


def test_failed_instrument_is_unavailable_never_a_number_and_missing_change_is_not_zero():
    svc, _ = service({"^BVSP": ProviderError("HTTP 404"), "USD-BRL": (5.0402, None)})
    text = svc.section_message(Section("x", "T", (IBOV, USD)))
    assert "Ibovespa: indisponível (HTTP 404)" in text
    assert "Dólar: 5,0402 R$" in text and "0,00" not in text and "%" not in text.split("Dólar")[1]


def test_quote_from_another_day_carries_its_date():
    prov = FakeProvider({"^BVSP": (1.0, 1.0)}, local(2026, 10, 16, 17, 0))
    svc = MarketService(prov, None, TZ, lambda: NOW)
    assert "(16/10)" in svc.section_message(Section("x", "T", (IBOV,)))


def test_messages_are_split_under_the_telegram_limit():
    blocks = ["x" * 2000, "y" * 2000, "z" * 500]
    parts = fmt.join_blocks(blocks)
    assert len(parts) == 2 and all(len(p) <= fmt.TELEGRAM_LIMIT for p in parts)
    assert len(fmt.join_blocks(["w" * 9000])[0]) <= fmt.TELEGRAM_LIMIT


# ------------------------------------------------------------
def test_bulletin_contains_sections_movers_and_filings():
    f = Filing("P1", "PETROBRAS", "Fato Relevante", "Dividendos", utc(2026, 10, 19, 12), "https://cvm/1")
    svc, _ = service(TABLE, FakeFilings([f]))
    text = "\n\n".join(svc.bulletin(profile()))
    assert "Mercado Brasil - 19/10/2026 10:25" in text
    assert "BOLSA\n• Ibovespa" in text and "CÂMBIO" in text
    assert "Altas\n• T0: 10,00  ▲ +5,00%\n• T1: 11,00  ▲ +3,00%" in text          # top 2 ups, best first
    assert "Quedas\n• T4: 14,00  ▼ -6,00%\n• T7: 17,00  ▼ -3,00%" in text         # worst first
    assert "1 de 8 papéis sem cotação" in text                                    # the failure is declared
    assert "FATOS RELEVANTES (CVM)\n• PETROBRAS - Dividendos (19/10)\n  https://cvm/1" in text


def test_movers_say_unavailable_when_every_quote_failed():
    svc, _ = service({})
    assert "indisponível (8/8 cotações falharam)" in svc.movers_message(profile())


def test_filings_source_down_is_reported_not_hidden():
    svc, _ = service(TABLE, FakeFilings(ProviderError("source unreachable")))
    assert "indisponível (source unreachable)" in svc.filings_message(profile())


def test_quote_command_validates_symbol():
    svc, prov = service({"PETR4.SA": (58.0, 0.5)})
    assert "PETR4.SA: 58,00" in svc.quote_message("petr4.sa")
    assert "inválido" in svc.quote_message("x; drop")
    assert prov.calls == ["PETR4.SA"]


# ------------------------------------------------------------
def test_alerts_fire_once_per_rule_day_and_direction_after_delivery(state, notifier):
    table = dict(TABLE, **{"^BVSP": (200000.0, -2.5), "USD-BRL": (5.0, 0.2)})
    svc, _ = service(table)
    r = BotRunner(profile(filings=None), "chat", svc, notifier, state, TZ)
    r.tick(NOW)
    alerts = [t for _c, t in notifier.sent if t.startswith("ALERTA")]
    assert len(alerts) == 1 and "Ibovespa: ▼ -2,50%" in alerts[0] and "Dólar" not in alerts[0]
    r._next_alert = None
    r.tick(NOW)                                                   # same day, same direction: silent
    assert len([t for _c, t in notifier.sent if t.startswith("ALERTA")]) == 1


def test_failed_delivery_does_not_consume_the_alert(state, notifier):
    svc, _ = service(dict(TABLE, **{"^BVSP": (200000.0, -2.5)}))
    r = BotRunner(profile(filings=None), "chat", svc, notifier, state, TZ)
    r._scheduled = lambda now: None          # isolate the alert path
    notifier.fail_next = 1
    r.tick(NOW)
    assert not any(t.startswith("ALERTA") for _c, t in notifier.sent)
    r._next_alert = None
    r.tick(NOW)
    assert any(t.startswith("ALERTA") for _c, t in notifier.sent)         # retried and delivered


def test_new_filing_alerts_skip_the_first_backlog_then_announce_only_new_ones(state, notifier):
    old = Filing("OLD", "VALE", "Fato Relevante", "antigo", utc(2026, 10, 19, 9))
    new = Filing("NEW", "PETROBRAS", "Fato Relevante", "novo", utc(2026, 10, 19, 13), "https://cvm/n")
    src = FakeFilings([old])
    svc, _ = service({}, src)
    r = BotRunner(profile(alerts=()), "chat", svc, notifier, state, TZ)
    r._scheduled = lambda now: None
    r.tick(NOW)
    assert notifier.sent == []                                    # baseline: the backlog is not an alert
    src.items = [new, old]
    r._next_alert = None
    r.tick(NOW)
    assert [t for _c, t in notifier.sent] == ["NOVO FATO RELEVANTE - PETROBRAS: novo\nhttps://cvm/n"]
    r._next_alert = None
    r.tick(NOW)
    assert len(notifier.sent) == 1                                # never twice


def test_alerts_are_silent_outside_the_window(state, notifier):
    svc, _ = service(dict(TABLE, **{"^BVSP": (1.0, -9.0)}))
    r = BotRunner(profile(filings=None), "chat", svc, notifier, state, TZ)
    r._scheduled = lambda now: None
    r.tick(local(2026, 10, 19, 21, 0))
    r.tick(local(2026, 10, 17, 12, 0))
    assert notifier.sent == []


# ------------------------------------------------------------
def test_scheduled_bulletin_is_sent_once_and_survives_a_restart(state, notifier):
    svc, _ = service(TABLE, FakeFilings([]))
    r = BotRunner(profile(alerts=(), filings=None), "chat", svc, notifier, state, TZ)
    r.tick(NOW)
    n = len(notifier.sent)
    assert n >= 1 and notifier.sent[0][1].startswith("Mercado Brasil")
    r.tick(local(2026, 10, 19, 10, 26))
    r2 = BotRunner(profile(alerts=(), filings=None), "chat", svc, notifier, state, TZ)   # "restart": same state store
    r2.tick(local(2026, 10, 19, 10, 27))
    assert len(notifier.sent) == n


def test_partial_delivery_resumes_at_the_failed_part_without_duplicates(state, notifier):
    big = {f"T{i}.SA": (10 + i, float(i)) for i in range(8)}
    table = dict(TABLE, **big)
    many = tuple(Instrument("yahoo", f"T{i}.SA", "N" * 60) for i in range(8))
    p = profile(alerts=(), filings=None, movers=None, sections=tuple(Section(f"s{k}", "S" * 40, many) for k in range(8)))
    svc, _ = service(table)
    r = BotRunner(p, "chat", svc, notifier, state, TZ)
    parts = svc.bulletin(p, NOW)
    assert len(parts) >= 2
    notifier.fail_next = 0
    # first part delivered, second fails
    calls = {"n": 0}
    orig = notifier.send

    def flaky(chat, text):
        calls["n"] += 1
        if calls["n"] == 2:
            raise DeliveryError("boom")
        orig(chat, text)

    notifier.send = flaky
    r.tick(NOW)
    assert len(notifier.sent) == 1
    notifier.send = orig
    r.tick(local(2026, 10, 19, 10, 27))          # still inside the 30 min catch-up window
    assert [t for _c, t in notifier.sent] == parts          # each part exactly once, in order
    r.tick(local(2026, 10, 19, 10, 28))
    assert len(notifier.sent) == len(parts)


def test_without_chat_nothing_is_sent(state, notifier):
    svc, _ = service(TABLE)
    BotRunner(profile(), "", svc, notifier, state, TZ).tick(NOW)
    assert notifier.sent == []


# ------------------------------------------------------------
class FakeApi(TelegramApi):
    def __init__(self, batches):
        self.batches = list(batches)
        self.offsets = []

    def get_updates(self, offset, timeout_s=25):
        self.offsets.append(offset)
        nxt = self.batches.pop(0) if self.batches else []
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def update(uid, chat, text):
    return {"update_id": uid, "message": {"chat": {"id": chat}, "text": text}}


def test_commands_answer_only_the_configured_chat_and_advance_the_offset(state, notifier):
    svc, _ = service(TABLE, FakeFilings([]))
    api = FakeApi([[update(10, 111, "/cambio"), update(11, 999, "/mercado"), update(12, 111, "/ajuda")]])
    r = BotRunner(profile(), "111", svc, notifier, state, TZ, api)
    assert r.poll_once() == 3
    texts = [t for c, t in notifier.sent]
    assert len(texts) == 2 and texts[0].startswith("CÂMBIO") and "/cotacao" in texts[1]
    assert all(c == "111" for c, _t in notifier.sent)
    assert r.unauthorized_dropped == 1                          # the stranger got NO reply
    assert state.get("offset:national") == "13"
    r.poll_once()
    assert api.offsets == [0, 13]


def test_unconfigured_chat_fails_closed(state, notifier):
    svc, _ = service(TABLE)
    r = BotRunner(profile(), "", svc, notifier, state, TZ, FakeApi([[update(1, 5, "/mercado")]]))
    r.poll_once()
    assert notifier.sent == [] and r.unauthorized_dropped == 1


def test_failed_reply_keeps_the_update_for_retry(state, notifier):
    svc, _ = service(TABLE)
    r = BotRunner(profile(), "111", svc, notifier, state, TZ, FakeApi([[update(5, 111, "/ajuda")]]))
    notifier.fail_next = 1
    assert r.poll_once() == 0 and state.get("offset:national") is None


def test_poll_conflict_propagates_so_the_loop_can_back_off(state, notifier):
    svc, _ = service(TABLE)
    r = BotRunner(profile(), "111", svc, notifier, state, TZ, FakeApi([PollConflict("409")]))
    with pytest.raises(PollConflict):
        r.poll_once()


def test_router_commands():
    svc, _ = service(TABLE, FakeFilings([]))
    router = CommandRouter(profile(), svc)
    assert "Comando desconhecido" in router.handle("/xyz")[0]
    assert router.handle("hello") == []
    assert "REGRAS DE ALERTA" in router.handle("/alertas@meubot")[0]
    assert "Use: /cotacao" in router.handle("/cotacao")[0]
    assert router.handle("/altas")[0].startswith("ALTAS E QUEDAS")
    assert "nenhum no período" in router.handle("/fatos")[0]


# ------------------------------------------------------------
def test_telegram_errors_never_leak_the_token():
    token = "123456:SECRET-token"

    def transport(url, payload, timeout):
        raise TransportError(401, f"Unauthorized for {url}")

    api = TelegramApi(token, transport)
    with pytest.raises(DeliveryError) as exc:
        api.send_message("1", "hi")
    assert token not in str(exc.value)


def test_send_retries_once_on_rate_limit_then_succeeds():
    seen = []

    def transport(url, payload, timeout):
        seen.append(url)
        if len(seen) == 1:
            raise TransportError(429, "Too Many Requests")
        return {"ok": True}

    TelegramApi("t", transport, sleep=lambda s: None).send_message("1", "hi")
    assert len(seen) == 2


def test_409_becomes_poll_conflict():
    def transport(url, payload, timeout):
        raise TransportError(409, "terminated by other getUpdates request")

    with pytest.raises(PollConflict):
        TelegramApi("t", transport).get_updates(0)


# ---------------------------------------------------------------------------------------------------- regressions (live run)
def test_reference_dates_keep_their_calendar_day_in_sao_paulo():
    """Found on the first live run: a reference day pinned at 00:00 UTC was shown as the previous day in BRT."""
    from market_bots.providers.bcb import BcbSgs
    from market_bots.providers.focus import BcbFocus

    sgs = BcbSgs(lambda u: [{"data": "19/10/2026", "valor": "13.65"}]).fetch(Instrument("sgs", "1178", "Selic"))
    assert sgs.as_of.astimezone(TZ).date().isoformat() == "2026-10-19"
    focus = BcbFocus(lambda u: {"value": [{"Data": "2026-10-16", "Mediana": 13.25}]}).fetch(
        Instrument("focus", "Selic:2026", "Focus"))
    assert focus.as_of.astimezone(TZ).date().isoformat() == "2026-10-16"


def test_tiny_moves_render_as_neutral_not_as_signed_zero():
    assert fmt.pct(0.004) == "■ 0,00%" and fmt.pct(-0.004) == "■ 0,00%" and fmt.pct(0.0) == "■ 0,00%"
    assert fmt.pct(0.006) == "▲ +0,01%"


def test_monthly_series_show_their_reference_month():
    ipca = Instrument("sgs", "433", "IPCA (último mês)", "% a.m.")
    prov = FakeProvider({"433": (0.82, None)}, utc(2026, 9, 1, 12))
    svc = MarketService(prov, None, TZ, lambda: NOW)
    assert "0,82 % a.m.  (ref. 09/2026)" in svc.section_message(Section("j", "J", (ipca,)))


def test_gold_in_reais_and_the_dollar_line_use_the_same_fx_source():
    from market_bots.providers import RoutingProvider

    seen = {"yahoo": [], "fx": []}

    class Rec:
        def __init__(self, name, table):
            self.name, self.table = name, table

        def fetch(self, ins):
            seen[self.name].append(ins.symbol)
            value, change = self.table[ins.symbol]
            return Quote(ins, value, utc(2026, 10, 19, 22), change)

    from market_bots.providers.gold import GoldBrlPerGram

    y, f = Rec("yahoo", {"GC=F": (4000.0, 1.0)}), Rec("fx", {"USD-BRL": (5.0, 1.0)})
    routed = RoutingProvider({"yahoo": y, "fx": f, "gold_brl": GoldBrlPerGram(y, f)})
    routed.fetch(Instrument("gold_brl", "", "Ouro"))
    assert seen == {"yahoo": ["GC=F"], "fx": ["USD-BRL"]}
