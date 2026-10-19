"""Behaviour of the three Telegram scripts under `work/`, with the network fully fenced off.

No test here can reach Telegram or any quote API: `urlopen` is replaced in each module by a recorder that
only answers the hosts the script is allowed to use. A request to anything else fails the test.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORK = REPO_ROOT / "work"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

pytestmark = pytest.mark.skipif(
    not WORK.is_dir(), reason="repository root with work/ not present (backend-only checkout)"
)

TOKEN = "123456:SECRET-TOKEN-VALUE"
CHAT = "4242"
FX_PAYLOAD = {
    "USDBRL": {"bid": "5.1234", "pctChange": "0.5"},
    "EURBRL": {"bid": "5.9", "pctChange": "-0.25"},
    "GBPBRL": {"bid": "6.8", "pctChange": "0"},
    "CHFBRL": {"bid": "5.5", "pctChange": "0.1", "high": "5.6", "low": "5.4"},
    "JPYBRL": {"bid": "0.034", "pctChange": "-0.1"},
    "EURUSD": {"bid": "1.08", "pctChange": "0.2"},
    "ARSBRL": {"bid": "0.005", "pctChange": "1.0"},
}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"work_{name}", WORK / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeNet:
    """Stands in for urllib's urlopen; records every call and answers only allow-listed hosts."""

    def __init__(self, allowed_hosts: tuple[str, ...]):
        self.allowed_hosts = allowed_hosts
        self.calls: list[dict] = []
        self.updates: list[dict] = []
        self.fail_get_updates: Exception | None = None
        self.fail_fx: Exception | None = None
        self.fail_send: Exception | None = None

    def sent_messages(self) -> list[dict]:
        return [c for c in self.calls if c["method"] == "sendMessage"]

    def __call__(self, request, timeout=None):
        url = request.full_url
        assert any(url.startswith(f"https://{host}/") for host in self.allowed_hosts), f"unexpected network call: {url}"
        body = dict(parse_qsl((request.data or b"").decode()))
        method = url.rsplit("/", 1)[-1] if "api.telegram.org" in url else "fx"
        self.calls.append({"url": url, "method": method, "body": body})
        if method == "fx":
            if self.fail_fx:
                raise self.fail_fx
            return _Response(FX_PAYLOAD)
        if method == "getUpdates":
            if self.fail_get_updates:
                raise self.fail_get_updates
            return _Response({"ok": True, "result": list(self.updates)})
        if method == "sendMessage":
            if self.fail_send:
                raise self.fail_send
            return _Response({"ok": True})
        raise AssertionError(f"unexpected Telegram method {method}")


class _Response:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _isolate(module, tmp_path, monkeypatch, net: FakeNet, env: dict[str, str]):
    state = tmp_path / ".state"
    monkeypatch.setattr(module, "STATE_DIR", state)
    monkeypatch.setattr(module, "LOG_PATH", state / "scheduler.log")
    monkeypatch.setattr(module, "ENV_PATH", tmp_path / "missing.env")
    if hasattr(module, "OFFSET_PATH"):
        monkeypatch.setattr(module, "OFFSET_PATH", state / "offset.json")
    monkeypatch.setattr(module, "urlopen", net)
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_FX_BOT_TOKEN", "TELEGRAM_FX_CHAT_ID"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def _log_text(tmp_path) -> str:
    path = tmp_path / ".state" / "scheduler.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _update(update_id: int, chat_id: int | str, text: str) -> dict:
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": text}}


# --- command poller ----------------------------------------------------------------
@pytest.fixture
def poller(tmp_path, monkeypatch):
    module = _load("market_command_bot")
    net = FakeNet(("api.telegram.org", "economia.awesomeapi.com.br"))
    _isolate(module, tmp_path, monkeypatch, net, {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT})
    return module, net


def test_every_advertised_command_has_a_route_and_unknown_commands_get_none(poller):
    module, net = poller
    advertised = re.findall(r"^(/\w+)", module.response_help(), flags=re.M)
    assert advertised  # the help text lists commands
    for command in advertised:
        if command == "/cambio":
            continue  # the only command that reaches the network; covered below
        assert module.route_command(command), command
    assert module.route_command("/nao_existe") is None
    assert module.route_command("/mercado@AlgumBot extra args") == module.response_market()
    assert net.calls == []  # static commands never touch the network


def test_static_lists_do_not_pretend_to_be_quotes(poller):
    module, _ = poller
    for command in ("/indices", "/acoes", "/etfs", "/fiis", "/bdrs", "/derivativos", "/spcx", "/rendafixa"):
        text = module.route_command(command)
        assert "R$" not in text and "%" not in text, command


def test_cambio_uses_the_quote_source_and_formats_pt_br(poller):
    module, net = poller
    text = module.route_command("/cambio")
    assert "R$ 5,1234 (+0,50%)" in text and "R$ 5,9000 (-0,25%)" in text
    assert [c["method"] for c in net.calls] == ["fx"]


@pytest.mark.parametrize("error", [URLError("down"), TimeoutError("slow"), HTTPError("u", 503, "x", {}, None)])
def test_cambio_without_a_source_shows_no_numbers(poller, error):
    module, net = poller
    net.fail_fx = error
    text = module.route_command("/cambio")
    assert "indisponivel" in text and "R$" not in text and "%" not in text


def test_formatters_never_turn_missing_data_into_a_number(poller):
    module, _ = poller
    assert module.fmt_number(None) == "n/d" and module.fmt_pct(None) == "n/d"
    assert module.fmt_pct("1.5") == "+1,50%" and module.fmt_pct("-2") == "-2,00%" and module.fmt_pct("0") == "0,00%"


def test_without_a_token_nothing_runs(poller, monkeypatch, tmp_path):
    module, net = poller
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    assert module.main() == 0
    assert net.calls == []
    assert "TELEGRAM_BOT_TOKEN" in _log_text(tmp_path)


def test_without_an_authorized_chat_the_bot_fails_closed(poller, monkeypatch, tmp_path):
    module, net = poller
    monkeypatch.delenv("TELEGRAM_CHAT_ID")
    net.updates = [_update(1, 999, "/help")]
    assert module.main() == 0
    assert net.calls == []                       # no getUpdates, no reply, no offset acknowledged
    assert not (tmp_path / ".state" / "offset.json").exists()
    assert "TELEGRAM_CHAT_ID" in _log_text(tmp_path)


def test_replies_only_to_the_authorized_chat_and_acknowledges_the_offset(poller, tmp_path):
    module, net = poller
    net.updates = [
        _update(10, CHAT, "/help"),
        _update(11, 777, "/help"),                # stranger: ignored
        _update(12, CHAT, "bom dia"),             # not a command: ignored
        _update(13, CHAT, "/desconhecido"),       # unknown command: ignored
        _update(14, CHAT, "/mercado"),
    ]
    assert module.main() == 0

    sent = net.sent_messages()
    assert [m["body"]["chat_id"] for m in sent] == [CHAT, CHAT]
    assert json.loads((tmp_path / ".state" / "offset.json").read_text())["offset"] == 15
    acks = [c for c in net.calls if c["method"] == "getUpdates" and c["body"].get("offset") == "15"]
    assert acks, "the highest update must be acknowledged at Telegram"
    assert "2 comando(s) respondido(s)" in _log_text(tmp_path)


def test_resumes_from_the_stored_offset(poller, tmp_path):
    module, net = poller
    (tmp_path / ".state").mkdir()
    (tmp_path / ".state" / "offset.json").write_text(json.dumps({"offset": 40}))
    module.main()
    first = net.calls[0]
    assert first["method"] == "getUpdates" and first["body"]["offset"] == "40"


def test_a_failing_poll_is_reported_without_leaking_the_token(poller, tmp_path):
    module, net = poller
    net.fail_get_updates = URLError("temporary failure")
    assert module.main() == 1
    assert net.sent_messages() == []
    assert TOKEN not in _log_text(tmp_path)


def test_a_corrupt_offset_file_falls_back_to_zero(poller, tmp_path):
    module, _ = poller
    (tmp_path / ".state").mkdir()
    (tmp_path / ".state" / "offset.json").write_text("{not json")
    assert module.read_offset() == 0


def test_long_replies_are_truncated_to_the_telegram_safe_size(poller):
    module, net = poller
    module.send_message(TOKEN, CHAT, "x" * 10_000)
    (call,) = net.sent_messages()
    assert len(call["body"]["text"]) == 3900


# --- FX radar ----------------------------------------------------------------------
@pytest.fixture
def fx(tmp_path, monkeypatch):
    module = _load("send_fx_telegram")
    net = FakeNet(("api.telegram.org", "economia.awesomeapi.com.br"))
    _isolate(module, tmp_path, monkeypatch, net, {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT})
    return module, net


def test_fx_without_credentials_sends_nothing(fx, monkeypatch):
    module, net = fx
    monkeypatch.delenv("TELEGRAM_CHAT_ID")
    assert module.main() == 1
    assert net.calls == []


def test_fx_sends_exactly_one_message_with_quotes(fx):
    module, net = fx
    assert module.main() == 0
    (message,) = net.sent_messages()
    text = message["body"]["text"]
    assert "Dolar comercial: R$ 5,1234 (+0,50%)" in text
    assert "Euro: R$ 5,9000 (-0,25%)" in text and "Fonte: AwesomeAPI Economia." in text
    assert message["body"]["chat_id"] == CHAT


def test_fx_prefers_its_dedicated_bot_and_chat(fx, monkeypatch):
    module, net = fx
    monkeypatch.setenv("TELEGRAM_FX_BOT_TOKEN", "999:FX")
    monkeypatch.setenv("TELEGRAM_FX_CHAT_ID", "555")
    module.main()
    (message,) = net.sent_messages()
    assert "/bot999:FX/" in message["url"] and message["body"]["chat_id"] == "555"


def test_fx_with_the_quote_source_down_still_sends_but_without_numbers(fx):
    module, net = fx
    net.fail_fx = URLError("down")
    assert module.main() == 0
    (message,) = net.sent_messages()
    assert "indisponivel" in message["body"]["text"] and "R$" not in message["body"]["text"]


def test_fx_reports_a_send_failure_and_does_not_leak_the_token(fx, tmp_path):
    module, net = fx
    net.fail_send = URLError("refused")
    assert module.main() == 1
    assert TOKEN not in _log_text(tmp_path)


# --- market radar ------------------------------------------------------------------
@pytest.fixture
def radar(tmp_path, monkeypatch):
    module = _load("send_market_telegram")
    net = FakeNet(("api.telegram.org",))
    _isolate(module, tmp_path, monkeypatch, net, {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT})
    return module, net


def test_market_radar_needs_credentials(radar, monkeypatch):
    module, net = radar
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    assert module.main() == 1 and net.calls == []


def test_market_radar_sends_one_message_made_only_of_symbols_never_prices(radar):
    module, net = radar
    assert module.main() == 0
    (message,) = net.sent_messages()
    text = message["body"]["text"]
    assert "Bloco desta rodada:" in text
    assert "R$" not in text and "%" not in text          # no currency amounts, no percentages
    assert [c["method"] for c in net.calls] == ["sendMessage"]   # it never fetches data


def test_market_radar_send_failure_is_reported(radar, tmp_path):
    module, net = radar
    net.fail_send = HTTPError("u", 500, "x", {}, None)
    assert module.main() == 1
    assert TOKEN not in _log_text(tmp_path)


# --- workflows: no duplicated consumers ------------------------------------------
def _workflow(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    data["on"] = data.pop(True, data.get("on"))   # YAML 1.1 parses the bare key `on` as True
    return data


def test_only_the_command_poller_is_scheduled_and_it_never_overlaps_itself():
    commands = _workflow("telegram-commands.yml")
    assert commands["on"]["schedule"] == [{"cron": "3/5 * * * *"}]
    assert commands["concurrency"] == {"group": "telegram-commands", "cancel-in-progress": False}
    for name in ("telegram-fx.yml", "telegram-market.yml"):
        assert set(_workflow(name)["on"]) == {"workflow_dispatch"}, name


def test_a_single_script_consumes_updates_per_token():
    consumers = [p.name for p in WORK.glob("*.py") if "getUpdates" in p.read_text(encoding="utf-8")]
    assert consumers == ["market_command_bot.py"]
