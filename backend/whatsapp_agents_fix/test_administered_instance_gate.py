"""Real execution of the administered-instance cross-talk gate from the
REAL, patched `webhooks/router.py` -- loaded by its actual deployed path
(backend/webhooks/router.py), not a copy, same technique as
test_send_whatsapp_text_real_execution.py.

Two things are executed for real here, not re-typed or AST-inspected:

  1. `_administered_instance_phones(settings)` -- called directly, it is
     already a standalone function with no DB dependency.
  2. The `managed_cross_talk = bool(sender_phone) and any(...)` expression
     inside `whatsapp_webhook` -- this one is NOT factored into its own
     function in the reviewed source, so it cannot be called directly.
     Instead, this file extracts the EXACT source text of that assignment
     statement, live, from `inspect.getsource(whatsapp_webhook)` via the
     `ast` module, and `exec()`s that exact text against real inputs. If
     the reviewed source ever changes that line, this test automatically
     runs the NEW text, not a stale copy -- it cannot silently drift from
     what the file actually says.

Honest limit, stated plainly: this does NOT execute `whatsapp_webhook`
end-to-end (that needs a FastAPI Request, webhook signature verification,
and Contact/Message upsert side effects this delivery's three source
files do not cover). What this DOES prove: given `managed_cross_talk ==
True` by the REAL code's REAL computation, `whatsapp_webhook` returns
(`WebhookAck(status="ignored")`) BEFORE its own later call to
`dispatch_inbound(...)` -- and `dispatch_inbound` is the ONLY place that
enqueues `whatsapp.twin_autopilot_check` / `whatsapp.process_inbound`,
the jobs that eventually call send_whatsapp_text and the provider. That
call-chain fact is confirmed by reading the real source (the early
`return` precedes `await dispatch_inbound(...)` textually, and
`dispatch_inbound`'s own source contains both enqueue calls), not by
executing a full webhook request end-to-end.
"""

from __future__ import annotations

import ast
import inspect
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

# Review fix (D) made router.py import `from services import
# conversation_control` -- load the real module first, same technique as
# test_send_whatsapp_text_real_execution.py, so that import resolves.
load_real_module("services.conversation_control", BACKEND_ROOT / "services" / "conversation_control.py")
router = load_real_module("webhooks.router", BACKEND_ROOT / "webhooks" / "router.py")


def _settings(*, personal_instance, owner_phone, store_instance, store_phone):
    return SimpleNamespace(
        evolution_personal_instance=personal_instance,
        whatsapp_owner_alert_phone=owner_phone,
        evolution_instance=store_instance,
        store_staff_notify_phone=store_phone,
    )


REAL_SETTINGS = _settings(
    personal_instance="Dário Marques Neto",
    owner_phone="+55 11 99999-0001",
    store_instance="store",
    store_phone="+55 11 99999-0002",
)


def test_administered_instance_phones_maps_both_configured_instances():
    # Real function, real call -- not a copy of its logic.
    result = router._administered_instance_phones(REAL_SETTINGS)
    assert result == {"Dário Marques Neto": "5511999990001", "store": "5511999990002"}


def test_administered_instance_phones_omits_unconfigured_slots():
    settings = _settings(personal_instance=None, owner_phone="+5511999990001", store_instance="store", store_phone=None)
    result = router._administered_instance_phones(settings)
    assert result == {}  # neither pair has BOTH instance and phone set


def _real_managed_cross_talk(*, administered, sender_phone, instance):
    """Extracts and executes the EXACT `managed_cross_talk = ...` assignment
    statement's live source text from webhooks/router.py's real
    `whatsapp_webhook` function -- see module docstring."""
    source = inspect.getsource(router.whatsapp_webhook)
    tree = ast.parse(source)
    target_stmt = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "managed_cross_talk" for t in node.targets
        ):
            target_stmt = node
            break
    assert target_stmt is not None, "managed_cross_talk assignment not found in the real source -- it moved or was renamed"
    segment = ast.get_source_segment(source, target_stmt)
    namespace = {
        "administered": administered,
        "sender_phone": sender_phone,
        "inbound": SimpleNamespace(instance=instance),
        "bool": bool,
        "any": any,
    }
    exec(compile(segment, "<extracted managed_cross_talk>", "exec"), namespace)
    return namespace["managed_cross_talk"]


def test_real_cross_talk_expression_fires_for_the_exact_twin_b2b_loop_shape():
    # The owner's personal-instance phone number showing up as the SENDER
    # on the store instance (or vice-versa) is exactly the Twin/B2B loop
    # shape from the 08/10 review.
    administered = router._administered_instance_phones(REAL_SETTINGS)
    result = _real_managed_cross_talk(administered=administered, sender_phone="5511999990001", instance="store")
    assert result is True


def test_real_cross_talk_expression_does_not_fire_on_its_own_instance():
    # The owner's number messaging through his OWN personal instance is
    # ordinary traffic, not cross-talk -- must not fire.
    administered = router._administered_instance_phones(REAL_SETTINGS)
    result = _real_managed_cross_talk(administered=administered, sender_phone="5511999990001", instance="Dário Marques Neto")
    assert result is False


def test_real_cross_talk_expression_does_not_fire_for_an_unrelated_client_number():
    administered = router._administered_instance_phones(REAL_SETTINGS)
    result = _real_managed_cross_talk(administered=administered, sender_phone="5511988887777", instance="store")
    assert result is False


def test_managed_cross_talk_return_happens_before_dispatch_inbound_is_even_called():
    """Structural confirmation (not execution) of the real call chain:
    `whatsapp_webhook` (this function) calls `dispatch_inbound` near its
    end, and ONLY `dispatch_inbound` contains the enqueue calls for
    `whatsapp.twin_autopilot_check` / `whatsapp.process_inbound` -- the
    jobs that eventually reach send_whatsapp_text and the provider. This
    confirms the early `return` on managed_cross_talk happens BEFORE
    `dispatch_inbound` is even called, so those enqueue calls can never
    be reached for a cross-talk message -- see module docstring's honest
    limit (this is read, not executed, for the enqueue side)."""
    webhook_source = inspect.getsource(router.whatsapp_webhook)
    cross_talk_pos = webhook_source.index("managed_cross_talk = bool(sender_phone)")
    return_pos = webhook_source.index("return WebhookAck", cross_talk_pos)
    dispatch_call_pos = webhook_source.index("await dispatch_inbound(", cross_talk_pos)
    assert cross_talk_pos < return_pos < dispatch_call_pos

    dispatch_source = inspect.getsource(router.dispatch_inbound)
    assert "twin_autopilot_check" in dispatch_source
    assert "process_inbound" in dispatch_source


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
