"""Review section 5 (loop entre bots): the Twin flow's own loop/flood-vs-
automation guard (rate_limiter-backed, see jobs/handlers.py's
twin_autopilot_check) only ever applied to the personal/Twin instance.
B2B, Azusa and Loja went straight from inbound message to
ai_orchestrator.run()/cognitive_pipeline.process() with nothing beyond
router.py's generic per-contact flood throttle -- no automation-specific
detection, no owner alert, unlike Twin.

This generalizes the SAME mechanism (same rate_limiter, same settings
fields, same incident_dedup owner-alert path) into a single shared
helper (`_loop_guard_or_alert`) now called from all three previously
unprotected branches of process_inbound_whatsapp_message. Tested here
against the real helper, the real rate_limiter (in-memory fallback, no
Redis needed for this), and the real conversation_control/incident_dedup
dedup machinery -- not a mock of any of them.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import load_real_module

HERE = Path(__file__).parent
BACKEND_ROOT = HERE.parents[0]
APP_STUB = str(HERE / "app_stub")
if APP_STUB not in sys.path:
    sys.path.insert(0, APP_STUB)

_REAL_MODULE_KEYS = (
    "services.output_safety", "services.conversation_control", "services.rate_limit", "jobs.handlers",
)


@pytest.fixture(scope="module", autouse=True)
def _real_modules():
    saved = {key: sys.modules.get(key) for key in _REAL_MODULE_KEYS}
    try:
        load_real_module("services.output_safety", BACKEND_ROOT / "services" / "output_safety.py")
        load_real_module("services.conversation_control", BACKEND_ROOT / "services" / "conversation_control.py")
        load_real_module("services.rate_limit", BACKEND_ROOT / "services" / "rate_limit.py")
        load_real_module("jobs.handlers", BACKEND_ROOT / "jobs" / "handlers.py")
        yield
    finally:
        for key, mod in saved.items():
            if mod is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = mod


@pytest.fixture
def handlers(_real_modules):
    return sys.modules["jobs.handlers"]


@pytest.fixture
def fresh_rate_limiter(_real_modules):
    """A brand-new RateLimiter instance (not the module-level singleton)
    so this test's windows never leak into any other test -- same
    in-memory fallback the real code uses when Redis is unreachable."""
    from utils.config import get_settings

    settings = get_settings()
    saved = {"redis_url": getattr(settings, "redis_url", None)}
    settings.redis_url = "redis://127.0.0.1:1"  # deliberately unreachable -- fast, deterministic fallback
    rate_limit_module = sys.modules["services.rate_limit"]
    instance = rate_limit_module.RateLimiter()
    instance._redis_available = False  # skip the (slow, doomed) connect attempt entirely
    original = sys.modules["jobs.handlers"].rate_limiter
    sys.modules["jobs.handlers"].rate_limiter = instance
    try:
        yield instance
    finally:
        sys.modules["jobs.handlers"].rate_limiter = original
        settings.redis_url = saved["redis_url"]


class _FakeJobService:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def enqueue(self, name, payload, delay_seconds=0):
        self.calls.append((name, payload))


def _settings_for_loop_guard():
    from utils.config import get_settings

    settings = get_settings()
    saved = {
        "whatsapp_twin_loop_guard_max_replies": settings.whatsapp_twin_loop_guard_max_replies,
        "whatsapp_twin_loop_guard_window_seconds": settings.whatsapp_twin_loop_guard_window_seconds,
        "whatsapp_owner_alert_phone": settings.whatsapp_owner_alert_phone,
    }
    settings.whatsapp_twin_loop_guard_max_replies = 2
    settings.whatsapp_twin_loop_guard_window_seconds = 3600
    settings.whatsapp_owner_alert_phone = "+5500000000099"
    return settings, saved


def _restore(settings, saved):
    for key, value in saved.items():
        setattr(settings, key, value)


@pytest.mark.asyncio
async def test_under_the_limit_does_not_suppress(handlers, fresh_rate_limiter, real_control_db):
    _, sessions = real_control_db
    settings, saved = _settings_for_loop_guard()
    contact = SimpleNamespace(id=42, name="Cliente B2B", phone="+5511999990000")
    message = SimpleNamespace(id=9500)
    try:
        jobs = _FakeJobService()
        async with sessions() as db:
            suppressed = await handlers._loop_guard_or_alert(db, settings, jobs, "b2b-sales", contact, message)
            await db.commit()
        assert suppressed is False
        assert jobs.calls == []
    finally:
        _restore(settings, saved)


@pytest.mark.asyncio
async def test_exceeding_the_limit_suppresses_and_alerts_the_owner(handlers, fresh_rate_limiter, real_control_db):
    """limit=2: the 3rd auto-reply attempt within the window must be
    suppressed and must alert the owner, with the alert's instance scope
    kept separate from the generic 'instance' payload field (review fix
    B's same concern, reused here)."""
    _, sessions = real_control_db
    settings, saved = _settings_for_loop_guard()
    contact = SimpleNamespace(id=42, name="Cliente Azusa", phone="+5511999990001")
    try:
        jobs = _FakeJobService()
        for i in range(2):
            message = SimpleNamespace(id=9600 + i)
            async with sessions() as db:
                suppressed = await handlers._loop_guard_or_alert(db, settings, jobs, "azusa-church", contact, message)
                await db.commit()
            assert suppressed is False

        message = SimpleNamespace(id=9602)
        async with sessions() as db:
            suppressed = await handlers._loop_guard_or_alert(db, settings, jobs, "azusa-church", contact, message)
            await db.commit()
        assert suppressed is True

        assert len(jobs.calls) == 1
        job_name, job_payload = jobs.calls[0]
        assert job_name == "whatsapp.send_text"
        assert job_payload["to"] == settings.whatsapp_owner_alert_phone
        assert job_payload["_twin_alert_contact_id"] == 42
        assert job_payload["_twin_alert_instance"] == "azusa-church"
        assert "instance" not in job_payload  # review fix (B)'s same concern: must not collide with sender routing
    finally:
        _restore(settings, saved)


@pytest.mark.asyncio
async def test_repeated_suppression_in_the_same_window_does_not_re_alert(handlers, fresh_rate_limiter, real_control_db):
    """Same incident, not a message storm to the owner -- incident_dedup's
    existing dedup window (reused, not duplicated) must still apply here."""
    _, sessions = real_control_db
    settings, saved = _settings_for_loop_guard()
    contact = SimpleNamespace(id=43, name="Cliente Loja", phone="+5511999990002")
    try:
        jobs = _FakeJobService()
        for i in range(2):
            message = SimpleNamespace(id=9700 + i)
            async with sessions() as db:
                await handlers._loop_guard_or_alert(db, settings, jobs, "dario-store", contact, message)
                await db.commit()

        for i in range(3):
            message = SimpleNamespace(id=9710 + i)
            async with sessions() as db:
                suppressed = await handlers._loop_guard_or_alert(db, settings, jobs, "dario-store", contact, message)
                await db.commit()
            assert suppressed is True

        assert len(jobs.calls) == 1, "alertou o proprietario mais de uma vez pelo mesmo incidente de loop"
    finally:
        _restore(settings, saved)


@pytest.mark.asyncio
async def test_different_instances_are_independent_windows(handlers, fresh_rate_limiter, real_control_db):
    """The same contact on two different instances (shouldn't realistically
    happen, but the rate limit key includes instance -- verify it actually
    does) must not share a loop-guard budget."""
    _, sessions = real_control_db
    settings, saved = _settings_for_loop_guard()
    contact = SimpleNamespace(id=42, name="Cliente Multi-instancia", phone="+5511999990003")
    try:
        for i in range(2):
            message = SimpleNamespace(id=9800 + i)
            async with sessions() as db:
                suppressed = await handlers._loop_guard_or_alert(db, settings, _FakeJobService(), "b2b-sales", contact, message)
                await db.commit()
            assert suppressed is False

        # A DIFFERENT instance, same contact, right after exhausting
        # b2b-sales's budget -- must still be allowed on its own window.
        message = SimpleNamespace(id=9802)
        async with sessions() as db:
            suppressed = await handlers._loop_guard_or_alert(db, settings, _FakeJobService(), "azusa-church", contact, message)
            await db.commit()
        assert suppressed is False
    finally:
        _restore(settings, saved)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
