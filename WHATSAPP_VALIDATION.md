# WhatsApp Validation Run — 2026-07-17

Validation of the WhatsApp session after reconnecting (QR re-scan). Two tests were run: a direct OpenWA gateway send, and a full backend-API round trip (after bootstrapping the first admin account — see `BOOTSTRAP_ADMIN.md`). Both hit the same underlying licensing block, but the backend test surfaced a real finding beyond that: **the backend reports success even when OpenWA rejects the send.**

## Direct Gateway test: **FAIL**

Sent directly to OpenWA's own REST API (`POST http://openwa:8002/sendText`), bypassing the backend entirely — the same call `providers/whatsapp/openwa/provider.py::OpenWAProvider.send_text` makes.

- **HTTP status**: `200 OK`
- **Response time**: `122.9ms`
- **OpenWA response payload**:
  ```json
  {"success": false, "response": "ERROR: Not a contact. Unlock this feature and support open-wa by getting a license: https://get.openwa.dev/l/5511993366903"}
  ```
- **Message ID**: none — no `Message` row exists at this layer (called OpenWA directly, not through the backend).
- **Delivery status**: not delivered. WhatsApp never received it.
- **OpenWA container logs** confirm the identical error at the same timestamp.

**Root cause**: an OpenWA (wa-automate) **licensing restriction** — the unlicensed/free tier refuses to send a first message to a number that isn't already a saved contact / existing chat thread on the connected session, to prevent unlicensed cold-outreach. `5511993366903` is not currently a known contact on this session. Not a bug, not related to the earlier disconnect/reconnect — OpenWA answered correctly and fast, actively evaluating and rejecting the send for a business reason (a different failure mode than "gateway unreachable").

## Backend API test (`POST /api/whatsapp/send-text`): **FAIL (silently)**

Required bootstrapping the first admin account first — see `BOOTSTRAP_ADMIN.md`. With a valid JWT:

- **HTTP status**: `200 OK`
- **Response time**: `238.5ms`
- **Response payload**: `{"status": "sent", "message_id": 1}`
- **Message ID**: `1` — a `Message` row **was** persisted (`direction=OUTBOUND`, correct content, `delivery_status` empty/null).

At the API-contract level this looks like a pass. It is not:

- **OpenWA container logs at the same timestamp show the identical rejection**: `ERROR: Not a contact. Unlock this feature and support open-wa by getting a license: https://get.openwa.dev/l/5511993366903`.
- The message was **never actually delivered** — WhatsApp never received it, exactly as in the direct test.

### Root cause (real finding, not infrastructure)

`OpenWAProvider.send_text` (`providers/whatsapp/openwa/provider.py`) returns whatever dict OpenWA's `/sendText` responds with, without checking the `success` field:

```python
async def send_text(self, to: str, content: str) -> dict:
    return await self._post("sendText", {"to": self._chat_id(to), "content": content})
```

`api/whatsapp.py::send_text` only treats a raised `WhatsAppProviderError` (transport failure — timeout, unreachable gateway) as an error; an HTTP-200 response with `success: false` inside the body is never inspected, so it falls through to `persist_outbound_message` and returns `{"status": "sent"}` regardless. The backend cannot currently distinguish "OpenWA delivered this" from "OpenWA rejected this for a business reason" — both look identical from the caller's side: `200`, a `message_id`, no error.

**This is a genuine gap, not something fixed in this validation run** — infrastructure is frozen per current priority (finishing the operational dashboard). Documented here so it isn't lost: `send_text` (and the other `send_*` methods, same shape) should check `result.get("success")` and raise `WhatsAppProviderError` when false, so a rejected send surfaces as a `502` to the caller and never gets marked `"sent"`.

## Verification checklist (as requested)

| Check | Result |
| --- | --- |
| Authentication | ✅ JWT issued and accepted (`/auth/login` → `/auth/me` → `200`) |
| Authorization | ✅ `CurrentUser` dependency satisfied; no role restriction on this endpoint (any authenticated user, matches `api/whatsapp.py`) |
| Persistence | ⚠️ A `Message` row was written (`id=1`) — but it records an attempt, not a confirmed delivery; `delivery_status` is empty because no delivery ack was ever received |
| EventBus | — not applicable to this path; `send_text`/`persist_outbound_message` don't publish an event (only the `whatsapp.process_inbound`/job-based send path does) |
| OpenWA delivery | ❌ Rejected — `ERROR: Not a contact...` |
| Backend logs | `INFO: "POST /api/whatsapp/send-text HTTP/1.1" 200 OK` — no error logged, consistent with the gap described above |
| OpenWA logs | `ERROR: Not a contact...` — the real outcome, invisible to the backend/caller |
| Response payload | `{"status": "sent", "message_id": 1}` |
| Message ID | `1` |

## Response times

| Test | Result | Time |
| --- | --- | --- |
| Direct OpenWA `sendText` | Rejected (200, success:false) | 122.9ms |
| `POST /api/auth/register` (bootstrap) | 201 | 864.5ms |
| `POST /api/auth/login` (bootstrap) | 200 | 447.8ms |
| Backend `/api/whatsapp/send-text` | 200, but not actually delivered | 238.5ms |

## Errors

- `ERROR: Not a contact. Unlock this feature and support open-wa by getting a license: https://get.openwa.dev/l/5511993366903` — reproduced identically in both the direct and backend-routed attempts, confirmed in `darioos-openwa-1` logs both times.

## Recommendations

1. **Fix the silent-failure gap** (see Root Cause above) — `OpenWAProvider.send_*` methods should check `success` and raise on `false`, so callers (and the `Message.delivery_status` field) reflect reality. Real, scoped, low-risk change — not done now because infrastructure is frozen for this priority window.
2. **To validate actual delivery**, send to a number that's already a known contact/conversation on this session, or obtain an open-wa license, or have the destination message the bot first (inbound isn't restricted).
3. The session reconnect itself remains confirmed healthy — `/health/ready` reports `whatsapp: ok`; this is purely a licensing/contact-list constraint on new outbound numbers, compounded by the backend not surfacing OpenWA's rejection.
4. First admin account now exists (`BOOTSTRAP_ADMIN.md`) — future validation runs no longer need to bootstrap.
