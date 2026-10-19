"""The audited Telegram inventory must stay true to the scripts and workflows it describes, and the admin
endpoint must stay read-only and credential-free."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from services.telegram_inventory import INVENTORY_AS_OF, POLLER_COMMANDS, build_inventory
from tests.test_admin_darius import admin_headers, admin_user, session_factory, user_headers  # noqa: F401

REPO_ROOT = Path(__file__).resolve().parents[2]
needs_repo = pytest.mark.skipif(
    not (REPO_ROOT / "work").is_dir(), reason="repository root with work/ not present (backend-only checkout)"
)


def _bot(bot_id: str):
    return next(b for b in build_inventory().bots if b.id == bot_id)


def _workflow_triggers(name: str) -> dict:
    data = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))
    return data.get("on", data.get(True))


# --- the inventory against the real files -----------------------------------------
@needs_repo
def test_poller_commands_match_the_routes_in_the_script():
    source = (REPO_ROOT / "work" / "market_command_bot.py").read_text(encoding="utf-8")
    routes = set(re.findall(r'^\s+"(/\w+)":', source, flags=re.M))
    assert routes == set(POLLER_COMMANDS)
    assert set(_bot("market-command-poller").commands) == routes


@needs_repo
@pytest.mark.parametrize("bot_id", ["market-command-poller", "fx-radar", "market-radar"])
def test_ship_it_entries_point_at_files_that_exist(bot_id):
    for relative in _bot(bot_id).source_files:
        assert (REPO_ROOT / relative).is_file(), relative


@needs_repo
def test_triggers_match_the_workflows():
    poller = _bot("market-command-poller")
    cron = [t.expression for t in poller.triggers if t.kind == "schedule"]
    assert cron == [e["cron"] for e in _workflow_triggers("telegram-commands.yml")["schedule"]]
    for bot_id, workflow in (("fx-radar", "telegram-fx.yml"), ("market-radar", "telegram-market.yml")):
        assert set(_workflow_triggers(workflow)) == {"workflow_dispatch"}
        assert [t.kind for t in _bot(bot_id).triggers] == ["manual"]
        assert _bot(bot_id).runtime.status == "sem_agendamento"


@needs_repo
@pytest.mark.parametrize(
    "bot_id,script",
    [("market-command-poller", "market_command_bot.py"), ("fx-radar", "send_fx_telegram.py"),
     ("market-radar", "send_market_telegram.py")],
)
def test_every_env_var_the_script_reads_is_declared(bot_id, script):
    source = (REPO_ROOT / "work" / script).read_text(encoding="utf-8")
    read = set(re.findall(r'env\.get\("(TELEGRAM_[A-Z_]+)"\)', source))
    declared = " ".join(_bot(bot_id).credentials)
    assert read and all(name in declared for name in read), (read, declared)


# --- invariants of what is claimed -------------------------------------------------
def test_claims_are_dated_and_evidenced_and_scp_x_stays_inconclusive():
    inventory = build_inventory()
    assert inventory.as_of == INVENTORY_AS_OF and inventory.live_state_available is False
    assert len({b.id for b in inventory.bots}) == len(inventory.bots)
    for bot in inventory.bots:
        if bot.runtime.status == "ativo_evidenciado":
            assert bot.runtime.evidence and bot.runtime.as_of, bot.id
        if bot.runtime.status == "inconclusivo":
            assert not bot.source_files and not bot.commands and not bot.triggers, bot.id
    spcx = _bot("monitor-spcx")
    assert spcx.runtime.status == "inconclusivo" and spcx.kind == "unknown"
    # the poller's /spcx text must not be presented as the monitor
    assert "NÃO é esse monitor" in spcx.runtime.detail


def test_counts_are_derived_from_the_entries_and_never_zero_filled():
    inventory = build_inventory()
    expected: dict[str, int] = {}
    for bot in inventory.bots:
        expected[bot.runtime.status] = expected.get(bot.runtime.status, 0) + 1
    assert inventory.counts_by_runtime_status == expected
    assert "nao_verificado" in expected and all(count > 0 for count in expected.values())


def test_no_secret_shaped_value_is_present():
    blob = build_inventory().model_dump_json()
    assert not re.search(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b", blob)       # Telegram bot token shape
    for bot in build_inventory().bots:
        for name in bot.credentials:
            assert "=" not in name                                    # names only, never NAME=value


def test_build_returns_independent_copies():
    first = build_inventory()
    first.bots[0].commands.append("/tampered")
    assert "/tampered" not in build_inventory().bots[0].commands


# --- admin endpoint ----------------------------------------------------------------
PATH = "/api/admin/telegram/bots"


@pytest.mark.asyncio
async def test_endpoint_requires_authentication_and_admin(client, user_headers):  # noqa: F811
    assert (await client.get(PATH)).status_code == 401
    assert (await client.get(PATH, headers=user_headers)).status_code == 403


@pytest.mark.asyncio
async def test_endpoint_returns_the_inventory_and_declares_live_state_unavailable(client, admin_headers):  # noqa: F811
    response = await client.get(PATH, headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["live_state_available"] is False and "estático" in body["live_state_note"]
    assert {b["id"] for b in body["bots"]} >= {"market-command-poller", "monitor-spcx"}
    assert body == build_inventory().model_dump(mode="json")


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
async def test_endpoint_has_no_write_methods(client, admin_headers, method):  # noqa: F811
    assert (await getattr(client, method)(PATH, headers=admin_headers)).status_code == 405
