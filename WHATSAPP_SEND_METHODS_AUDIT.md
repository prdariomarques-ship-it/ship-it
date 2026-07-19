# WhatsApp `send_*` Methods — `success` Field Audit

Investigation only, no code changed. Prepared 2026-07-18, following up on the gap first noted in `WHATSAPP_VALIDATION.md` (2026-07-17) and referenced in `RELEASE_SUMMARY_v1.3.1.md`. This audit confirms it with fresh, live evidence and traces every call site.

## Confirmed: yes, this happens

Every `send_*` method on `OpenWAProvider` — the currently configured provider (`whatsapp_provider: "openwa"` in `backend/utils/config.py`) — can return `{"status": "sent", "message_id": <int>}` to its caller even when OpenWA reports `success: false`. Reproduced live today, not just cited from yesterday's doc.

## Affected methods

All 5 methods `OpenWAProvider` implements, in `backend/providers/whatsapp/openwa/provider.py`:

| Method | Lines | OpenWA endpoint |
|---|---|---|
| `send_text` | 52–55 | `sendText` |
| `send_image` | 57–68 | `sendImage` |
| `send_file` | 70–81 | `sendFile` |
| `send_audio` | 83–84 | `sendAudio` |
| `send_location` | 86–97 | `sendLocation` |

There is no `send_video` method — checked `backend/providers/whatsapp/base.py`'s abstract interface (5 `@abstractmethod` send methods total, no video) and every concrete provider; it doesn't exist anywhere in this codebase, so it's not "unaudited," it's simply not a thing that can be affected.

**Every one of the 5 is affected identically** — they all route through the same two helper methods, and the gap lives in those, not in any individual method:

```python
# provider.py:40-46
async def _post(self, endpoint: str, args: dict) -> dict:
    return await self._request(
        "POST", f"{self._base_url}/{endpoint}",
        json_body={"args": args}, headers=self._headers(),
    )
```

`_request` (`backend/providers/whatsapp/base.py:143-214`, shared by every provider) only raises when the HTTP call itself fails (`response.raise_for_status()` on a 4xx/5xx, or a transport error) — it has no concept of a body-level `success` field, because that's an OpenWA-specific contract, not a universal one (see "Why only OpenWA" below). When OpenWA answers `200 OK` with `{"success": false, ...}` in the body, `raise_for_status()` sees a perfectly good `200` and returns normally. Nothing downstream ever looks at `success`.

## Exact code paths

Three places a rejected send silently becomes "sent," all sharing the same root cause:

**1. HTTP API — `backend/api/whatsapp.py`** (5 routes, one per method, e.g. `send_text` at lines 53–64):
```python
try:
    await get_whatsapp_provider().send_text(payload.to, payload.content)
except WhatsAppProviderError as exc:
    raise _bad_gateway(exc) from exc
message = await persist_outbound_message(db, payload.to, payload.content, MessageMediaType.TEXT)
return SendResponse(message_id=message.id)
```
Note the return value of `send_text(...)` isn't even assigned to a variable — the dict OpenWA returned (`success`, `response`) is discarded outright. The only thing that could stop `persist_outbound_message` from running is an *exception*, and `success: false` never raises one. Identical shape for `send_image`, `send_file`, `send_audio`, `send_location` (lines 67–129).

**2. Job handler — `backend/jobs/handlers.py:42-51`** (`whatsapp.send_text` job, used for AI auto-replies and the agent's `send_whatsapp_message` tool call, per its own docstring):
```python
await get_whatsapp_provider().send_text(to, content)
await persist_outbound_message(db, to, content)
```
Same gap, second call site — this one has *no* try/except around the provider call at all in the handler itself (job-level retry only helps for actual exceptions, and `success: false` doesn't raise one, so retry never triggers either).

**3. `backend/services/messaging.py::persist_outbound_message`** (lines 20-30) — its own docstring states the precondition this whole bug violates:
> "Call this AFTER the provider send succeeds — never before, so a failed send doesn't leave a message row claiming something was delivered."

For OpenWA, "the provider send succeeds" is currently indistinguishable from "the provider call didn't throw," and those are not the same thing.

## Example payloads

**Reproduced live today**, direct against the OpenWA gateway (bypassing the backend, same call `send_text` makes):
```
POST http://openwa:8002/sendText
{"args":{"to":"5511900000001@c.us","content":"probe - nao e uma mensagem real"}}

→ HTTP 200
{"success":false,"response":"ERROR: Not a contact. Unlock this feature and support open-wa by getting a license: https://get.openwa.dev/l/5511993366903"}
```

Same shape, different number, documented independently yesterday in `WHATSAPP_VALIDATION.md`:
```
{"success": false, "response": "ERROR: Not a contact. Unlock this feature and support open-wa by getting a license: https://get.openwa.dev/l/5511993366903"}
```

Confirmed cause in both: OpenWA's free-tier licensing restriction on first messages to a number that isn't already a contact/existing chat on the session. That's the one root cause reproduced so far — the code path has no partial check, so any other reason OpenWA might answer `success: false` for (rate limiting, blocked number, malformed recipient, etc.) would hit the exact same gap; not testing every possible rejection reason doesn't change that the check itself is simply absent.

What the caller actually receives from the backend for this exact rejected send:
```
HTTP 200
{"status": "sent", "message_id": 1}
```
(`message_id: 1` from yesterday's run — a real `Message` row, `direction=OUTBOUND`, `delivery_status` permanently empty because no genuine WhatsApp delivery ack will ever arrive for a message WhatsApp never received.)

## Why only OpenWA (not Baileys/Evolution/Official)

Checked all three other providers' `send_*` implementations — none reference a `success` field either, but that's because their gateways signal failure via HTTP status codes (a `4xx`/`5xx`), which `_request`'s `raise_for_status()` already catches and turns into `WhatsAppProviderError` → `502` correctly. Evolution API's contract, e.g., has no body-level success flag to check in the first place. OpenWA's easy-api is the one gateway in this codebase that returns `200 OK` for both successes and logical rejections, distinguished only by a body field — an unusual contract that the shared, provider-agnostic `_request` helper has no way to know about, and that only `OpenWAProvider` itself could check.

## Test coverage: none

- `backend/tests/test_providers.py` has zero assertions involving `send_text`/`success` for any provider.
- `backend/tests/test_whatsapp_pipeline.py` mocks the method out entirely: `patch("...OpenWAProvider.send_text", new=AsyncMock(return_value={"status": "ok"}))` — an arbitrary shape unrelated to OpenWA's real `{"success", "response"}` contract, and never inspected by the code under test anyway. Every pipeline test that touches sending assumes success by construction; none exercise a rejection.

## Impact assessment

- **Scope**: every outbound WhatsApp send in the system — dashboard-triggered (`/api/whatsapp/send-*`) and AI-agent-triggered (`whatsapp.send_text` job, used by automatic replies and the agent's own tool call) both go through the same unguarded path.
- **What actually happens**: a rejected send is persisted as a normal outbound `Message` (never flagged, never retried, `delivery_status` silently stuck empty forever) and reported `200`/`"sent"` to whoever asked — a human via the dashboard, or the agent orchestrator, which has no way to know its reply never reached the customer.
- **Trust/data-integrity issue, not a crash**: nothing errors, nothing logs at `ERROR` level on the backend side (confirmed in `WHATSAPP_VALIDATION.md`: backend log shows a clean `200 OK`; only OpenWA's own container log shows the real rejection) — this fails exactly the way that's hardest to notice operationally.

## Production-critical?

**Yes.** Not an outage-causing bug (nothing crashes, `/health/ready` stays green — same reason the original `health_check` bug hid for as long as it did), but a **silent correctness/data-integrity issue on every outbound message send**, live in production right now, on both the human-facing and the AI-agent-facing send paths. It directly contradicts a precondition another part of the codebase already documents and assumes is being upheld (`persist_outbound_message`'s own docstring). Severity: high, urgency: not an emergency (it's a pre-existing condition, not a regression from anything shipped today), but it should not sit unticketed.

## Recommended fix (not implemented — investigation only, per instructions)

Check `result.get("success")` and raise `WhatsAppProviderError` when it's `False`, so a rejection surfaces as a real `502` to every caller and never reaches `persist_outbound_message`. Cheapest correct place to put it: once, inside `OpenWAProvider._post` (provider.py:40-46) — every one of the 5 `send_*` methods already routes through it, so a single change fixes all 5 without touching each method individually. Mirrors the exact shape of the fix already applied to `health_check()` in commit `fa7c8ff`.

## Recommendation: open a dedicated GitHub issue first

Per your instruction — yes, recommend a dedicated issue before implementing anything, separate from Issue #2 (which is scoped to `getConnectionState`, an unrelated read-only introspection call). Suggested scope for that issue: this exact finding — title along the lines of *"OpenWA: send_* methods report success even when OpenWA rejects the send"* — referencing this file, `WHATSAPP_VALIDATION.md`, the three exact code paths above, and the acceptance criteria: `success` checked in `_post`, existing tests updated to assert on the real OpenWA response shape (not the current unrelated mock), and a regression test added for the rejection case reproduced above.
