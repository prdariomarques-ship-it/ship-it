"""FAKE settings -- a plain namespace with the fields jobs/handlers.py
actually reads. `evolution_personal_instance = None` is the one choice
that matters for this test suite: it makes
_owner_audio_personal_instance() always False, so _owner_audio_send_guard
short-circuits to `return True` without touching any repository -- exactly
right for testing on a generic, non-personal instance, which is what
every scenario in this round uses."""

from types import SimpleNamespace

_settings = SimpleNamespace(
    evolution_personal_instance=None,
    evolution_instance="store",
    whatsapp_twin_mode_enabled=True,
    whatsapp_twin_loop_guard_max_replies=3,
    whatsapp_twin_loop_guard_window_seconds=300,
    whatsapp_twin_idle_timeout_seconds=120,
    whatsapp_owner_alert_phone="+5500000000001",
    store_staff_notify_phone="+5500000000002",
    auto_reply_enabled=True,
    auto_reply_max_per_contact_per_minute=5,
    store_whatsapp_enabled=True,
)


def get_settings():
    return _settings
