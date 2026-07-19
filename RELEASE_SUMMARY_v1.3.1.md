# Dario OS v1.3.1 Release Summary

Prepared 2026-07-18, as a final release audit. All figures below were re-verified live during this audit (test suites re-run, endpoints re-queried, `docker compose ps` re-checked), not copied from prior docs without confirmation. Where this audit's findings disagree with an earlier document, that's called out explicitly rather than silently reconciled.

## Release status

| | |
|---|---|
| **Tagged release** | `v1.3.1` (tag `5bdb6a7`, 2026-07-18) |
| **Current `HEAD`** | `fa7c8ff` — **5 commits ahead of `v1.3.1`'s tag**, 1 of which is a runtime code change (see "Fixes included") |
| **Running backend image** | Built from `fa7c8ff` (rebuilt and redeployed during this audit) — i.e. **production is currently running code that is not part of the tagged `v1.3.1` release or its CHANGELOG entry** |
| **Overall health** | `docker compose ps`: all 11 services `Up`. Of those, 5 have a configured Docker healthcheck (`alertmanager`, `backend`, `grafana`, `postgres`, `prometheus`) — all report `healthy`. The other 6 (`caddy`, `frontend`, `jaeger`, `n8n`, `openwa`, `qdrant`, `redis`) have no healthcheck configured; verified individually below instead of trusting a blank `docker compose ps` field |
| **Deployment status** | Stable, no crash-restarts (`RestartCount=0` on every container checked). `frontend` shows 4 process-start banners spread across ~13 hours in its logs, most recently 13:54 UTC — consistent with the whole stack having been recreated together at that time (matches every other container's uptime), not a crash loop |

## Components

| Component | Status | Evidence |
|---|---|---|
| **Backend** | ✅ Healthy | Docker healthcheck: `healthy`. `GET /health` → `{"status":"ok"}`. `GET /health/ready` → `{"status":"ok","checks":{"database":"ok","redis":"ok","qdrant":"ok","whatsapp":"ok"}}` |
| **Frontend** | ✅ Up, responding | No Docker healthcheck configured. Verified directly: `GET /` inside the container returns `200` with full HTML. Next.js 14.2.35 |
| **OpenWA** | ✅ Authenticated, connected | Session authenticated this audit cycle (QR scan, account ending `6903`). `isConnected` → `true`. Test message sent and confirmed received by the account owner. `getConnectionState()` throws a `TypeError` — tracked, see "Known issues" |
| **PostgreSQL** | ✅ Healthy | Docker healthcheck: `healthy` |
| **Redis** | ✅ Healthy | No Docker healthcheck; confirmed via backend's own dependency check (`checks.redis: ok`) |
| **Qdrant** | ✅ Healthy | No Docker healthcheck; confirmed via backend's own dependency check (`checks.qdrant: ok`) |
| **Event Bus** | ✅ Operational | Not a separate service — in-process pub/sub (`backend/events/bus.py`) with best-effort Redis fanout, degrades silently if Redis is down. No dedicated health endpoint; healthy by construction since both the backend process and Redis are healthy |

## Fixes included

This section separates what the audit was asked to report against what the repository's own history actually attributes to each version — they don't fully agree:

| Fix | Actually shipped in | Notes |
|---|---|---|
| **Mobile sidebar responsive fix** | **v1.3.0**, not v1.3.1 (commit `d64b8be`, GA tag) | `CHANGELOG.md` and `FINAL_RELEASE_SUMMARY.md` both confirm this. `v1.3.1` is a pure backend patch — no frontend commit exists in its range |
| **OpenWA `health_check` fix** | **Not yet released** — commit `fa7c8ff`, made and deployed during this session/audit, **after** the `v1.3.1` tag and after `FINAL_RELEASE_SUMMARY.md` had already closed the v1.3.1 cycle | Corrects `health_check()` treating any non-empty OpenWA response (including `{"success": false, ...}`) as healthy; now checks `success` explicitly and falls back to `isConnected()`. Verified with `pytest` (85 passed) and live against the actually-erroring `getConnectionState` endpoint |
| **Documentation updates** | v1.3.1 (docs-only commits `8493a96`, `5bdb6a7`, `de2d393`) | `VERSION.json` bump, `VERSION_HISTORY.md` and `CHANGELOG.md` backfill for the previously-undocumented v1.3.0/v1.3.1 gap |
| *(v1.3.1's actual code fixes, for completeness)* | v1.3.1 (commit `2929256`) | `validation.py`/`jobs/router.py`: wired unused email/phone validators into `agents/tools/domain.py`, fixed `validate_phone_e164` to accept numbers without `+`, removed a duplicate/inferior `/jobs/{id}/cancel` endpoint. These are the fixes the tag `v1.3.1` actually corresponds to |

## Known issues

- **GitHub Issue #2** — `OpenWA: investigate getConnectionState() TypeError compatibility issue`. Status: **Open**. `getConnectionState()` throws (`Store.State.default` is `undefined` — a WhatsApp Web internal module-shape change, same class of drift as the LID issue already documented in `docker/openwa/Dockerfile`). Non-blocking: `isConnected()` (DOM-based, unaffected) is used as the fallback and confirms the session is genuinely connected.
- **Not yet tracked in an issue — found during this audit, still present in current code**: `WHATSAPP_VALIDATION.md` (2026-07-17) documents that `OpenWAProvider.send_text` (and the other `send_*` methods) never inspect OpenWA's `success` field. A rejected send (confirmed reproducible: OpenWA's free-tier licensing block on first messages to non-contacts) still returns `{"status": "sent", "message_id": ...}` to the caller and is persisted as such — **a silent false-positive on message delivery**, not just on health status. Re-confirmed present in `backend/api/whatsapp.py`/`OpenWAProvider.send_text` as of this audit. This is a more serious instance of the same bug class just fixed in `health_check()`, and has no tracking issue yet.
- **Version-string drift** (not a runtime bug, but affects the trustworthiness of any future audit): three different values currently claim to be "the version" —`backend/utils/config.py`'s `app_version` constant (`0.2.1`, what `/health` actually returns), `backend/VERSION.json` (`1.3.0-rc1`), and the git tag / CHANGELOG (`v1.3.1`). None agree.

## Test summary

| | Result | Notes |
|---|---|---|
| **Backend automated tests** | **864 passed**, 0 failed (293.9s) | Re-run live during this audit (`pytest -q`), not copied from `VERSION.json` — matches it exactly |
| **Frontend automated tests** | **240 passed** across 32 files, 0 failed (60.8s) | Re-run live during this audit (`vitest run`), matches `VERSION.json` exactly |
| **End-to-end WhatsApp validation** | ✅ Pass (this audit cycle) | Full QR-auth flow completed live, session reached `CONNECTED`, a real test message was sent via `sendText` and confirmed received by the recipient. Supersedes the **failed** 2026-07-17 validation (`WHATSAPP_VALIDATION.md`), which hit the licensing/non-contact rejection described above — that underlying gap in `send_text` is still unfixed (see "Known issues"), this run simply didn't hit it |
| **Health checks** | ✅ Pass | `/health`, `/health/ready` both green with the corrected `whatsapp` check; cross-verified against the raw OpenWA endpoints directly, not just trusted at face value |

## Production readiness

**v1.3.1, as tagged, is production-ready** — the CHANGELOG's own claim (864/864 backend tests, no migration, no frontend change, lint clean) holds up under live re-verification.

With two qualifications an audit shouldn't paper over:

1. **What's actually running is not what's tagged.** The live backend is one commit (`fa7c8ff`) ahead of `v1.3.1`, carrying an unreleased fix. It's a net improvement (corrects a false-positive health check) and is tested, but it means "production" and "`v1.3.1`" are no longer the same thing until that commit is folded into a release.
2. **The silent send-failure gap** (`send_text` not checking `success`) is a real, reproducible, currently-shipping issue — not introduced by this audit, but not fixed by it either. It doesn't block v1.3.1 (it predates it and isn't a regression), but it's a live correctness gap in a code path already flagged once (`WHATSAPP_VALIDATION.md`) and still open.

## Recommendations for v1.4.0

In priority order:

1. **Fix `OpenWAProvider.send_text`/`send_image`/`send_file`/`send_audio`/`send_location` to check `success`** and raise `WhatsAppProviderError` on `false`, per `WHATSAPP_VALIDATION.md`'s own recommendation from 2026-07-17 — this is the highest-severity open item, silently masking failed deliveries as sent.
2. **Resolve GitHub Issue #2** (`getConnectionState` `TypeError`) — root-cause it against the current wa-automate/WhatsApp Web version, decide whether to patch it (as already done for the LID `sendMessage` issue in `docker/openwa/Dockerfile`) or formally adopt `isConnected` as the primary check and remove the now-dead code path.
3. **Reconcile the three conflicting version numbers** (`app_version` constant, `VERSION.json`, git tag) into one source of truth — ideally `VERSION.json` generated at release time and `app_version` read from it, so `/health`'s version field is never stale again.
4. **Tag/release the `health_check` fix** (`fa7c8ff`) formally — e.g. `v1.3.2` — rather than leaving it as an unreleased commit sitting on top of a closed release cycle.
5. **Add Docker healthchecks** for the 6 services currently without one (`frontend`, `openwa`, `redis`, `qdrant`, `caddy`, `n8n`, `jaeger`), so `docker compose ps` reflects real status instead of requiring manual verification, as this audit had to do.
6. Add a regression test for the `getConnectionState` → `isConnected` fallback in `health_check()` (already an acceptance criterion on Issue #2, worth calling out as a discrete task).
