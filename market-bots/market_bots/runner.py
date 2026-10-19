"""One bot = one profile: scheduled bulletin, alert pass, and command polling. All time and I/O are injected."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .commands import CommandRouter
from .domain import Profile
from .ports import Notifier, StateStore
from .schedule import due_slot, in_window
from .service import MarketService
from .telegram import DeliveryError, TelegramApi

log = logging.getLogger("market_bots.runner")


class BotRunner:
    def __init__(self, profile: Profile, chat_id: str, service: MarketService, notifier: Notifier, state: StateStore,
                 tz: ZoneInfo, api: TelegramApi | None = None) -> None:
        self.profile = profile
        self._chat = chat_id
        self._svc = service
        self._notify = notifier
        self._state = state
        self._tz = tz
        self._api = api
        self._router = CommandRouter(profile, service)
        self._next_alert: datetime | None = None
        self._warned_no_chat = False
        self.unauthorized_dropped = 0

    # ---- schedule + alerts (called every few seconds by the main loop) --------------------------------------
    def tick(self, now: datetime) -> None:
        if not self._chat:
            if not self._warned_no_chat:
                log.error("[%s] no chat id configured: nothing will be sent", self.profile.id)
                self._warned_no_chat = True
            return
        self._scheduled(now)
        self._alerts(now)

    def _scheduled(self, now: datetime) -> None:
        pid = self.profile.id
        slot = due_slot(now, self.profile.schedule, self.profile.weekdays_only, self.profile.catchup_minutes,
                        self._state.get(f"slot:{pid}"), self._tz)
        if slot is None:
            return
        parts = self._svc.bulletin(self.profile, now)
        done = 0
        progress = self._state.get(f"progress:{pid}")   # "<slot>|<parts already delivered>"
        if progress and progress.split("|", 1)[0] == slot:
            done = int(progress.split("|", 1)[1])
        for i, text in enumerate(parts):
            if i < done:
                continue
            try:
                self._notify.send(self._chat, text)
            except DeliveryError as exc:
                log.error("[%s] bulletin %s part %d/%d not delivered: %s", pid, slot, i + 1, len(parts), exc)
                return          # slot stays open: the next tick (inside the catch-up window) resumes at this part
            self._state.set(f"progress:{pid}", f"{slot}|{i + 1}")
        self._state.set(f"slot:{pid}", slot)
        log.info("[%s] bulletin %s delivered (%d message(s))", pid, slot, len(parts))

    def _alerts(self, now: datetime) -> None:
        p = self.profile
        if not (p.alerts or p.filings) or not in_window(now, p.alert_window, p.weekdays_only, self._tz):
            return
        if self._next_alert is not None and now < self._next_alert:
            return
        self._next_alert = now + timedelta(minutes=p.alert_interval_minutes)
        for alert in self._svc.alerts(p, self._state, now):
            try:
                self._notify.send(self._chat, alert.text)
            except DeliveryError as exc:
                log.error("[%s] alert not delivered (will retry next pass): %s", p.id, exc)
                return
            self._state.set(alert.key, now.isoformat())     # committed only after delivery

    # ---- commands ---------------------------------------------------------------------------------------------
    def poll_once(self) -> int:
        """Handle pending chat commands. Returns the number of updates consumed. Raises PollConflict (409)."""
        if self._api is None:
            return 0
        pid = self.profile.id
        offset = int(self._state.get(f"offset:{pid}") or 0)
        updates = self._api.get_updates(offset)
        consumed = 0
        for u in updates:
            uid = u.get("update_id")
            if not isinstance(uid, int):
                continue
            msg = u.get("message") or {}
            chat = str((msg.get("chat") or {}).get("id", ""))
            text = msg.get("text")
            if self._chat and chat == self._chat and isinstance(text, str):
                try:
                    for reply in self._router.handle(text):
                        self._notify.send(self._chat, reply)
                except DeliveryError as exc:
                    log.error("[%s] reply not delivered, update %d will be retried: %s", pid, uid, exc)
                    return consumed        # offset NOT advanced for this update
            else:
                # Fail closed: an unknown chat (or no configured chat) never gets an answer; only a counter is kept.
                self.unauthorized_dropped += 1
            self._state.set(f"offset:{pid}", str(uid + 1))
            consumed += 1
        return consumed


def make_clock() -> Callable[[], datetime]:
    from datetime import timezone

    return lambda: datetime.now(timezone.utc)
