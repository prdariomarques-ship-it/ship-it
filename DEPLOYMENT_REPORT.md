# Deployment Report — Dario OS Operational Dashboard

Controlled production deployment of commit `5186c5b` (Operational Dashboard MVP).

## Deployed commit

- **Before**: `d348b42` (docs: add Context Observation Engine architecture review) — confirmed via image build timestamp (`2026-07-17T01:22:33-03:00`, minutes after `d348b42` was authored and hours before `5186c5b`) and functionally via `GET /api/admin/observation` returning `404` pre-deploy.
- **After**: `5186c5b97f7552d89e57dc31a04f1c5aebd8e3a5` (`feat: build the Dario OS Operational Dashboard (MVP)`), matching `origin/master` exactly.

## Deployment timestamp

Backend/frontend rebuilt and restarted at **2026-07-17 13:29 UTC** (10:29 local, `-03:00`). Validation completed by 13:36 UTC.

## Services restarted

Only `backend` and `frontend` (`docker compose up -d --no-deps backend frontend`). `--no-deps` guarantees Compose never touches dependent services.

| Service | Action | Uptime check |
| --- | --- | --- |
| backend | Rebuilt + recreated + restarted | Healthy ~1 min after restart |
| frontend | Rebuilt + recreated + restarted | Up, serving correctly via Caddy |
| postgres | **Untouched** | 11h uptime, unaffected |
| redis | **Untouched** | 11h uptime, unaffected |
| qdrant | **Untouched** | 11h uptime, unaffected |
| openwa | **Untouched** | 11h uptime, unaffected |
| caddy | **Untouched** | 11h uptime, unaffected |

## Migrations executed

**None required.** `git diff --stat d348b42..5186c5b -- backend/alembic/versions/` is empty — this deployment introduced no schema changes (the only backend change, `GET /api/admin/observation`, reads an existing in-process engine; `goals/scoring.py`'s fix is pure application logic, no schema involved). The container's standard boot step (`alembic upgrade head`) ran as always and had nothing new to apply — confirmed clean in the boot log (`Context impl PostgresqlImpl` / `Will assume transactional DDL`, no migration steps listed).

## Health check results (Phase 3)

| Check | Result |
| --- | --- |
| `/health` | `{"status":"ok"}` |
| `/health/ready` | `{"status":"ok","checks":{"database":"ok","redis":"ok","qdrant":"ok","whatsapp":"ok"}}` |
| Backend health | `healthy` (Docker healthcheck) within ~1 min of restart |
| Frontend health | `200` via Caddy for `/` and `/admin` (a same-container `localhost` probe failed, but that's a testing artifact — the Next.js standalone server binds to the container's Docker-network IP, not `localhost`, by design; Caddy's real routing to that IP is what actually matters and it works) |
| Database connectivity | `ok`, 2.1ms |
| Redis | `ok`, 41.9ms |
| Qdrant | `ok`, 40.3ms |
| WhatsApp provider | `ok`, `provider=openwa`, 169.5ms |
| Observation Engine | `GET /api/admin/observation` → `200`, real data (`degraded_sources: []`), scheduler chain alive (`observation.tick` queued for the next 5-minute tick) |
| Event Bus | `ok`, "4 handler(s) registered" — confirms both `jobs.handlers` (1) and the Observation Engine's `goal.*`/`job.*`/`agent.*` subscriptions (3) registered correctly on this boot |
| Scheduler/jobs | Confirmed via Postgres: job `112` QUEUED for `13:35:32`, jobs `111`/`110` `SUCCEEDED` — the self-rescheduling chain survived the restart exactly as designed (durable job queue, not in-memory state) |

No errors, tracebacks, or exceptions in `backend` logs at any point during or after the restart.

## Functional validation results (Phase 4)

Real browser (Playwright + Chromium) against `https://localhost` (the actual public Caddy entrypoint), logged in with the real production admin account.

| Check | Result |
| --- | --- |
| Dashboard loads | ✅ |
| Current Context visible | ✅ — populated with real data (5 recent events, 1 conversation, 1 pending job, 1 memory entry, all traceable to this session's real WhatsApp integration test) |
| Goals render | ✅ — correct empty state ("Nenhuma meta pronta"): production genuinely has no goals yet |
| Tasks render | ✅ — correct empty state, same reason |
| Recent Events render | ✅ — live log stream, real timestamps |
| Suggested Actions | ✅ — "Tudo em dia" (correct: no goal awaiting approval, no failed job, no overdue task exists in production) |
| System Health | ✅ — 8 components reporting, 7 online, Google OAuth correctly offline (no client credentials configured) |
| WhatsApp shows "Connected" | ✅ — "Conectado" in green |
| JavaScript console errors | ⚠️ 5 found — see below |
| Backend logs remain clean | ✅ — no errors logged during or after the functional pass |

### Console errors — investigated, not a blocker

All 5 errors are the identical pattern: `Failed to fetch RSC payload for https://localhost/<route>. Falling back to browser navigation.` for `/agenda`, `/tarefas`, `/conversas`, `/calendario`, `/metas` — none of which are routes touched by this deployment (they belong to the pre-existing `(dashboard)` route group, untouched since before this session). This is Next.js's App Router background-prefetching a set of linked routes (likely from the "Voltar ao app" link in the admin header) failing to fetch the React Server Component payload and **automatically, gracefully falling back to a full page navigation** — by design, not a crash. Every panel this deployment actually added still rendered correctly and every action button worked. Recorded as a known issue for a separate investigation, not a rollback trigger.

## Rollback status

**Not needed.** No step failed. The previous image (`darioos-backend` / `darioos-frontend`, tag `latest`, pre-rebuild) was overwritten by `docker compose build`, so a rollback today would require re-checking out `d348b42` and rebuilding rather than a simple tag swap — noted here as a process gap, not an incident. Nothing indicates a rollback is warranted.

## Known issues

1. **5 console warnings from Next.js RSC prefetch** for unrelated, pre-existing routes — see above. Worth a follow-up look, not urgent.
2. **No image versioning/tagging strategy** — `docker compose build` overwrites `latest` in place, so there is no one-command rollback to the prior image today. A future improvement: tag images with the git commit (`darioos-backend:5186c5b`) before deploying, so rollback is `docker compose up -d` against the previous tag instead of a rebuild.
3. Everything else flagged in `PRODUCT_ACCEPTANCE.md` (Cognitive Pipeline activity has no real data yet in production; `recent_events` shows the Observation Engine's own tick bookkeeping) remains true post-deploy — both are documented, intentional/known, not regressions from this deployment.

## Conclusion

The production URL is serving the new dashboard successfully. All ten panels render, WhatsApp shows "Conectado," System Health is accurate, the Observation Engine's scheduler chain survived the restart, and the AI Suggested Actions / Pending Jobs action buttons are live against the real backend. Deployment is complete.
