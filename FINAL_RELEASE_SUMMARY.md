# Final Release Summary — v1.3.1

Closes the v1.3.1 release cycle. Prepared 2026-07-18.

## Current state

| | |
|---|---|
| **Current version** | v1.3.1 |
| **Latest commit (`HEAD`, `origin/master`)** | `de2d393f00508b9a23cfa6d36f361d31848b78df` — "docs: add v1.3.0 and v1.3.1 entries to CHANGELOG.md" |
| **Latest tag** | `v1.3.1` → `5bdb6a7eb99248e1902478556367fe23a65f3867` ("docs: record v1.3.0 GA and v1.3.1 patch in version history") |
| **Deployed backend commit** | `2929256182394d8ccd96ec25a1d30f6b170ca912` — the last commit with a runtime behavior change; confirmed live via `GET /api/version`, matching `backend/VERSION.json` |
| **Production status** | Healthy. `database: ok`, `redis: ok`, `qdrant: ok`. `whatsapp: error: WhatsAppProviderUnhealthy` — pre-existing (`openwa` session needs QR re-auth), unrelated to this release, not a blocker |
| **Working tree / origin sync** | Clean, nothing uncommitted; `origin/master` == local `HEAD` (`de2d393`) |

Note the two trailing docs-only commits (`5bdb6a7`, `de2d393`, both after the
deployed code commit `2929256`) don't require a redeploy — no application
code changed. `v1.3.1`'s tag sits one commit before the very latest
(`de2d393`, the CHANGELOG addition), which is a docs-only, non-functional
gap, consistent with how this repo has always tagged (the tag marks the
release point; trailing chore/docs commits are normal and not re-tagged
for).

## Test counts

| | Backend | Frontend |
|---|---|---|
| v1.3.0-rc1 (2026-07-17) | 883 | 231 |
| v1.3.0 GA (2026-07-18) | 886 | 240 |
| **v1.3.1 (2026-07-18, current)** | **864** | **240** |

Backend count dropped 886 → 864 by removing 21 dead-code tests
(`validate_url`/`validate_file_path`, confirmed to have zero real input
surface anywhere in the backend) — not a regression. Frontend untouched
this cycle, count carried over unrun from v1.3.0.

## Release timeline

```
v1.2.0 (2026-07-11)
  └─ v1.3.0-rc1 (2026-07-17)   AI Operator Center, Memory & Timeline,
     │                         Daily Briefing, Action Center.
     │                         RC1_AUDIT.md: readiness 82%, 1 Critical +
     │                         several Medium findings.
     │
     ├─ d64b8be                Critical fix: AdminShell mobile-responsive
     │                         sidebar drawer. Readiness → 90%.
     │
  └─ v1.3.0 (2026-07-18, tag @ d64b8be)   GA — same feature set as the RC,
     │                         now with the Critical fix included.
     │                         Immutable; not moved during this cycle.
     │
     ├─ 2929256                fix: resolves both open Medium findings
     │                         (validation.py dead-code cleanup + real-gap
     │                         wiring; jobs/router.py duplicate-endpoint
     │                         removal). Deployed and verified live.
     ├─ 8493a96, 5bdb6a7,
     │  de2d393                chore/docs: VERSION.json bump, version-
     │                         history backfill, CHANGELOG entries.
     │
  └─ v1.3.1 (2026-07-18, tag @ 5bdb6a7)   Patch release.
```

## Documentation sync check

All four release documents cross-checked and consistent as of this
summary:

- `CHANGELOG.md` — `[1.3.1]` and `[1.3.0]` entries added (the file
  previously jumped straight from `[1.2.0]` to `[1.3.0-rc1]` with no GA
  or patch entries).
- `VERSION_HISTORY.md` — same gap, same fix: `v1.3.0` and `v1.3.1`
  sections added.
- `PROJECT_STATUS.md` — test counts, version timeline, and the stale
  "mobile sidebar not yet fixed" claim corrected.
- `RELEASE_READINESS.md` — the analysis behind classifying this cycle's
  changes as PATCH rather than MINOR, written before the tag was created.

All four agree on: 864 backend / 240 frontend tests, deployed commit
`2929256`, `v1.3.0` tag at `d64b8be`.

## Outstanding items (not part of this release, carried forward)

From `CURRENT_PROJECT_STATE.md` / `RELEASE_READINESS.md`, unrelated to
v1.3.1 and not newly introduced by it:

1. `whatsapp` provider unhealthy — operational (QR re-auth), not code.
2. Optional: parallelize `/api/admin` + `/api/admin/status` (latency).
3. `ROADMAP_v2.md`'s stated v1.3.0 scope (integration reliability) still
   diverges from what actually shipped under that version number.

None of these block the v1.3.1 tag or its documentation.

---

**v1.3.1 release cycle: closed.**
