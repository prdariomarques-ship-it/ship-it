"""Composition root + CLI.

  python -m market_bots run                 long-running service (scheduler + alerts + command polling)
  python -m market_bots once <profile> [section]
                                            print a live bulletin/section to stdout. NEVER sends anything.
  python -m market_bots check-config        validate profiles.toml and the environment, then exit
  python -m market_bots healthcheck         exit 0 if the service loop beat in the last 120 s

Environment:
  MB_CONFIG      path to profiles.toml            (default ./profiles.toml)
  MB_STATE_DIR   volume for state/outbox/heartbeat (default ./data)
  MB_SEND        off (default: dry-run, nothing leaves the process) | on
  MB_PROFILES    comma list of profile ids to run (default: all)
  <profile.token_env> / <profile.chat_env>         per-bot Telegram credentials (only read when MB_SEND=on)
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import ConfigError, Settings, load
from .domain import Profile
from .providers import RoutingProvider
from .providers.cvm import CvmIpe
from .runner import BotRunner
from .service import MarketService
from .state import FileStateStore
from .telegram import DryRunNotifier, PollConflict, TelegramApi, TelegramNotifier

log = logging.getLogger("market_bots")
HEARTBEAT_MAX_AGE_S = 120
TICK_SECONDS = 5


class StartupError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def select_profiles(settings: Settings, env: Mapping[str, str]) -> list[Profile]:
    wanted = [p.strip() for p in env.get("MB_PROFILES", "").split(",") if p.strip()]
    known = {p.id for p in settings.profiles}
    unknown = [w for w in wanted if w not in known]
    if unknown:
        raise StartupError(f"MB_PROFILES names unknown profile(s): {', '.join(unknown)} (known: {', '.join(sorted(known))})")
    return [p for p in settings.profiles if not wanted or p.id in wanted]


def send_mode(env: Mapping[str, str]) -> bool:
    raw = env.get("MB_SEND", "off").strip().lower()
    if raw not in ("on", "off"):
        raise StartupError(f'MB_SEND must be "on" or "off" (got "{env.get("MB_SEND")}")')
    return raw == "on"


def build_runners(settings: Settings, env: Mapping[str, str], state_dir: Path, send: bool) -> list[BotRunner]:
    tz = ZoneInfo(settings.timezone)
    state = FileStateStore(state_dir / "state.json")
    service = MarketService(RoutingProvider(), CvmIpe(), tz, _utcnow)
    runners: list[BotRunner] = []
    for profile in select_profiles(settings, env):
        token, chat = env.get(profile.token_env, "").strip(), env.get(profile.chat_env, "").strip()
        if send:
            missing = [n for n, v in ((profile.token_env, token), (profile.chat_env, chat)) if not v]
            if missing:
                raise StartupError(
                    f"MB_SEND=on but {', '.join(missing)} is not set for profile '{profile.id}'. "
                    f"Set it, or leave the profile out with MB_PROFILES.")
            api = TelegramApi(token)
            runners.append(BotRunner(profile, chat, service, TelegramNotifier(api), state, tz, api))
        else:
            runners.append(BotRunner(profile, chat or "dry-run", service,
                                     DryRunNotifier(state_dir / "outbox.log", profile.id), state, tz, None))
    return runners


def _poll_loop(runner: BotRunner, stop: threading.Event) -> None:
    pid = runner.profile.id
    while not stop.is_set():
        try:
            runner.poll_once()
        except PollConflict:
            log.error("[%s] 409 Conflict: another instance is polling this bot token (VPS and PC at the same time?). "
                      "Command polling for this bot is paused for 10 minutes; scheduled sends continue.", pid)
            stop.wait(600)
        except Exception as exc:  # noqa: BLE001 - the loop must survive transient network errors
            log.warning("[%s] poll failed: %s", pid, exc)
            stop.wait(5)


def run(env: Mapping[str, str]) -> int:
    settings = load(Path(env.get("MB_CONFIG", "profiles.toml")))
    state_dir = Path(env.get("MB_STATE_DIR", "data"))
    state_dir.mkdir(parents=True, exist_ok=True)
    send = send_mode(env)
    runners = build_runners(settings, env, state_dir, send)
    log.info("market-bots up: send=%s profiles=%s", "ON" if send else "off (dry-run)", [r.profile.id for r in runners])
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    threads: list[threading.Thread] = []
    if send:
        for r in runners:
            t = threading.Thread(target=_poll_loop, args=(r, stop), name=f"poll-{r.profile.id}", daemon=True)
            t.start()
            threads.append(t)
    heartbeat = state_dir / "heartbeat"
    while not stop.is_set():
        now = _utcnow()
        for r in runners:
            try:
                r.tick(now)
            except Exception:  # noqa: BLE001 - one bot failing must not stop the other
                log.exception("[%s] tick failed", r.profile.id)
        heartbeat.write_text(now.isoformat(), encoding="utf-8")
        stop.wait(TICK_SECONDS)
    log.info("market-bots stopping")
    for t in threads:
        t.join(timeout=3)
    return 0


def healthcheck(env: Mapping[str, str]) -> int:
    hb = Path(env.get("MB_STATE_DIR", "data")) / "heartbeat"
    try:
        age = time.time() - hb.stat().st_mtime
    except OSError:
        return 1
    return 0 if age < HEARTBEAT_MAX_AGE_S else 1


def once(env: Mapping[str, str], profile_id: str, section: str | None) -> int:
    settings = load(Path(env.get("MB_CONFIG", "profiles.toml")))
    tz = ZoneInfo(settings.timezone)
    service = MarketService(RoutingProvider(), CvmIpe(), tz, _utcnow)
    profile = next((p for p in settings.profiles if p.id == profile_id), None)
    if profile is None:
        print(f"unknown profile {profile_id!r}; known: {', '.join(p.id for p in settings.profiles)}", file=sys.stderr)
        return 2
    if section:
        sec = next((s for s in profile.sections if s.id == section), None)
        if sec is None:
            print(f"unknown section {section!r}; known: {', '.join(s.id for s in profile.sections)}", file=sys.stderr)
            return 2
        print(service.section_message(sec))
    else:
        print("\n\n---- (nova mensagem) ----\n\n".join(service.bulletin(profile)))
    return 0


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stdout)
    cmd = argv[0] if argv else "run"
    try:
        if cmd == "run":
            return run(env)
        if cmd == "check-config":
            settings = load(Path(env.get("MB_CONFIG", "profiles.toml")))
            send = send_mode(env)
            build_runners(settings, env, Path(env.get("MB_STATE_DIR", "data")), send)
            print(f"OK: {len(settings.profiles)} profile(s), send={'on' if send else 'off'}")
            return 0
        if cmd == "healthcheck":
            return healthcheck(env)
        if cmd == "once" and len(argv) >= 2:
            return once(env, argv[1], argv[2] if len(argv) > 2 else None)
    except (ConfigError, StartupError) as exc:
        print(f"REFUSING TO START: {exc}", file=sys.stderr)
        return 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
