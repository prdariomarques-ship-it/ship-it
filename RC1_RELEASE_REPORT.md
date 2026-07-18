# RC1 Release Report — v1.3.0-rc1

## Version

**1.3.0-rc1** — Release Candidate 1 for v1.3.0, the "Product Evolution" cycle on top of v1.2.0.

## Tag

`v1.3.0-rc1` (annotated), pushed to `origin`.

## Commit

`bfa84f92283676e6ecbccd1f078fa62af135e49d` (branch `master`)

## Release date

2026-07-17 (audit and stabilization) / 2026-07-18 (tag cut and version metadata, UTC)

## Features included

Four features, each with its own detailed doc:

| Feature | Where | Doc |
| --- | --- | --- |
| **AI Operator Center** | `/admin` | `AI_OPERATOR.md` |
| **Memory & Timeline** | `/admin/timeline` | `MEMORY_TIMELINE.md` |
| **Daily Briefing** | `/admin/briefing` | `DAILY_BRIEFING.md` |
| **Action Center** | `/admin/action-center` | `ACTION_CENTER.md` |

Plus this release-engineering pass itself: `GET /api/version`, `VERSION.json`, and the RC1 stabilization fixes below. Full feature narrative: `RELEASE_NOTES.md`. Full changelog entry: `CHANGELOG.md` (`[1.3.0-rc1]`).

## Test summary

| Suite | Result |
| --- | --- |
| Backend (pytest) | 883/883 passing, +3 for `/api/version` in this release-engineering pass |
| Frontend (Vitest) | 231/231 passing |
| TypeScript (`tsc --noEmit`) | clean |
| ESLint (`next lint`) | clean, zero warnings |
| Production build (`next build`) | clean, 27 routes |
| Browser validation | Action Center execution flow, Action Preview panel, Daily Briefing, Timeline — zero console errors on the final pass (isolated demo environment, real seeded data) |

## Readiness score: 82%

Per `RC1_AUDIT.md`: zero regressions, every suite green, one Critical finding (no mobile-responsive admin sidebar — real, but doesn't block the primary desktop-admin use case), a handful of Medium findings that need a product decision rather than a mechanical fix, and two safe deduplication fixes already applied during the audit. Full findings list, severities, and rationale: `RC1_AUDIT.md`.

## Known limitations

Carried over from `KNOWN_LIMITATIONS.md` (unchanged by this cycle — none of these four features touch Google integrations, Circuit Breaker, backup, or the areas that file covers) plus what's new this cycle:

- **Critical**: admin dashboard sidebar has no mobile-responsive collapse — unusable on a ~375px viewport. See `RC1_AUDIT.md` Finding #1.
- **Medium**: `backend/services/validation.py`'s four validation functions have zero callers — dead code or a real gap, needs a decision. See `RC1_AUDIT.md` Finding #2.
- **Medium**: three `jobs/router.py` endpoints have no frontend caller — needs confirmation they're not used by something outside the frontend. See `RC1_AUDIT.md` Finding #3.
- **Medium**: `/api/admin` and `/api/admin/status` are the two slowest admin endpoints (0.7–1.0s, vs. 0.02–0.12s for everything else) — likely fixable by parallelizing their sequential health checks. See `RC1_AUDIT.md` Finding #4.
- Everything already tracked in `KNOWN_LIMITATIONS.md` (Google retry/circuit-breaker, WhatsApp QR pairing not in-dashboard, Settings page read-only, Qdrant backup, etc.) still applies unchanged.

## Deployment status

**Not deployed to production.** This RC was validated against an isolated demo environment (SQLite, seeded data, ports 8010/3300) — the production containers (`darioos-backend-1`, `darioos-frontend-1`) have not been rebuilt or restarted as part of this release. The tag and `VERSION.json` exist so a deploy can happen deliberately, on request, rather than as a side effect of tagging. `VERSION.json` is bundled into the backend image on the next `docker compose build backend` (already `COPY`-ed via the existing `COPY . .` in `backend/Dockerfile` — no Dockerfile change needed).

## Rollback instructions

Since nothing was deployed, there is nothing to roll back yet. For when this RC (or the eventual v1.3.0 GA) does get deployed:

1. **Fastest rollback — redeploy the previous tag:**
   ```bash
   git checkout v1.2.0
   docker compose up -d --build backend frontend
   ```
2. **Verify the rollback**: `curl https://<host>/api/version` should report `"version": "1.2.0"` (or whatever `VERSION.json` existed at that tag — note v1.2.0 predates `VERSION.json`/`/api/version`, so a rollback to it will 404 on that specific endpoint until a `VERSION.json` is backfilled for it, which is expected and not itself a failure signal).
3. **No database migration to reverse** — this cycle added zero schema changes (all four features compose existing data; the only backend additions are `POST /admin/actions/log`, `GET /api/version`, and query-parameter extensions to `GET /admin/logs`, none of which touch the schema).
4. Return to `master` when ready to roll forward again: `git checkout master`.

## Next milestone: v1.3.0 GA

1. Resolve the Critical finding (mobile-responsive `AdminShell`/`AdminSidebar`) or make an explicit, documented decision to ship GA without it.
2. Get a human decision on the two "needs a decision" Medium findings (`validation.py` dead functions, unused `jobs/router.py` endpoints) and act on it.
3. Optionally address the `/api/admin` + `/api/admin/status` latency (parallelize health checks) — not blocking, but the clearest low-effort win available.
4. Deploy this RC (or the GA build that follows) to production, then re-tag `v1.3.0` (drop the `-rc1` suffix) at the exact commit that was actually deployed.
5. Update `PROJECT_STATUS.md`'s "Timeline de versões" and `VERSION_HISTORY.md` once GA ships.
