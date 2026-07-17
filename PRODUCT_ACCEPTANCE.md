# Product Acceptance Review — Dario OS Operational Dashboard

Real, browser-driven verification of the dashboard (Playwright + the project's own pre-installed Chromium) — not just "it compiles." Two environments were used, deliberately:

- **Isolated demo backend** (temporary SQLite DB, its own uvicorn process on `127.0.0.1:8010`, seeded through the real API — registration, goals, tasks, calendar events — never touching production). Used for every data-heavy panel, so screenshots show a populated, working system instead of an empty new account.
- **Live production system** (`darioos-backend-1` / `darioos-frontend-1`, real data, already-verified WhatsApp session). Used only for the one thing the isolated demo cannot honestly show: a genuinely connected WhatsApp session and real System Health signals from the actual deployed stack.

No production data was created, modified, or deleted to produce these screenshots.

## Acceptance checklist

| # | Check | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Open the dashboard in the browser | ✅ | Logged in via Playwright, navigated to `/admin`, both environments |
| 2 | Every widget renders correctly | ✅ | `dashboard-full.png` — all 10 panels present, no crashed/blank widgets |
| 3 | Current Context is visible | ✅ | `current-context.png` — 15 items observed, all 7 dimensions populated |
| 4 | Goals render | ✅ | `active-goals.png` — 3 ready goals, priority badges, progress bars |
| 5 | Tasks render | ✅ | `todays-tasks.png` — 3 tasks, correctly flagged "Atrasada" where overdue |
| 6 | Recent Events render | ✅ | `recent-events.png` — live log stream, filterable, real timestamps |
| 7 | System Health updates | ✅ | `production-whatsapp-connected.png` — 9 real component checks, all correctly reported (7 online, 2 offline for real reasons) |
| 8 | WhatsApp status is displayed | ✅ | `production-whatsapp-connected.png` — "Conectado" in green, queue/sent counts, link to detail page |
| 9 | Observation Engine information is visible | ✅ | `current-context.png` header: "Gerado 16s atrás · scheduler · 15 itens observados" — freshness, trigger, and item count all visible |
| 10 | No empty screens, placeholder cards, or unintentional broken layouts | ⚠️ see below | One intentional empty state, one pre-existing-deploy gap — both explained, neither is a broken layout |

### On check 10, in detail

Two things render as "empty" or "errored" during this review — both understood and neither a layout bug:

- **Cognitive Pipeline activity is an intentional empty state** (`"Nenhuma execução do pipeline ainda"`) — no WhatsApp message was processed by the Cognitive Pipeline in either environment during this review (the demo never received an inbound message; production's real conversations happened before this dashboard existed and aren't `source="cognitive_pipeline"` log rows from a live run today). This is `EmptyState`, not a blank/broken card — same component and visual language every other panel uses for "nothing yet." Confirmed correct behavior, not a bug.
- **`production-whatsapp-connected.png` shows the Current Context panel erroring** with `Not Found`. This is expected: that screenshot was taken against the **currently-deployed** production backend, which predates this session's work — `GET /api/admin/observation` doesn't exist in that running container yet. It is not a code defect (the isolated demo, running this session's actual code, renders the identical panel correctly — see `current-context.png`); it is a deployment-order artifact, listed under "Remaining work" below.

## Screenshots

All under `docs/screenshots/dashboard-mvp/`:

- `dashboard-full.png` — the complete dashboard, one screen, full scroll height (3880px), isolated demo environment, fully populated.
- `current-context.png` — Context Observation Engine panel: freshness, trigger, 7 dimensions with counts and content.
- `suggested-actions.png` — AI Action Center: an awaiting-approval goal with a working Approve button, a failed job with a working Retry button, three overdue-task alerts, one suggested-next-goal card.
- `active-goals.png`, `todays-tasks.png`, `calendar.png` — the three domain panels, each with real seeded content.
- `pending-jobs.png` — the live `observation.tick` job, queued, with a Cancel button.
- `pipeline-activity.png` — the intentional empty state discussed above.
- `recent-events.png` — the real-time log stream (see `BUG_DISCOVERY_REPORT.md`-adjacent note in `docs/OBSERVATION_REVIEW.md` about `observation.tick`'s own bookkeeping dominating this feed — visible here, not hidden).
- `production-whatsapp-connected.png` — live production system: WhatsApp "Conectado", full System Health grid, all real.

## Known limitations

- **Cognitive Pipeline activity has no real data to show yet in either environment reviewed here** — correct empty state, not exercised end-to-end in this review (would require an actual inbound WhatsApp message to flow through the pipeline).
- **`recent_events` is dominated by `observation.tick`'s own job-lifecycle log entries** (visible in `recent-events.png` — a long run of `Job N started`/`succeeded` lines). Documented in `docs/OBSERVATION_REVIEW.md` as a known trade-off, not fixed in this review — filtering it out is a product decision (how much of the engine's own bookkeeping should count as a "recent event"?) better made with a real consumer in mind.
- **Local screenshot infrastructure required real debugging** (Caddy's automatic HTTP→HTTPS redirect, a stale server process silently squatting on a port, `next dev`/`next build` sharing one `.next` directory). All resolved during this review; none of it reflects a product defect — recorded here only for anyone reproducing this process later.
- **`Pipeline` and per-panel automated interaction tests** (e.g., clicking Approve/Retry/Cancel end-to-end in an automated test) were not added in this review — verified manually via Playwright instead. Recommended as a follow-up `e2e/dashboard.spec.ts`.

## Remaining work

1. **Deploy the updated backend to production.** `GET /api/admin/observation` and the `goals/scoring.py` fix (see `BUG_DISCOVERY_REPORT.md`) only exist in this session's code, not yet in the running `darioos-backend-1` container. Until redeployed, production's Current Context panel will show the "Not Found" error captured in `production-whatsapp-connected.png`.
2. **Deploy the updated frontend to production** (`darioos-frontend-1`) so the new dashboard is actually reachable at the real `/admin` URL — today it only exists in this session's local demo/dev instances.
3. Optional: an automated Playwright spec covering the new panels and their action buttons, so this acceptance pass doesn't have to be repeated by hand next time.

## Overall readiness score: **85%**

Every required panel is built, wired to real (mostly pre-existing) endpoints, renders correctly with real data, and the interactive actions (approve/retry/cancel) are present and call real endpoints. The 15% gap is entirely deployment, not construction: the code isn't live in production yet, and there's no automated regression coverage for the new UI (backend is fully tested — 875/875 — the frontend relies on this manual review). Once deployed, this is a usable, one-screen operational view of Dario OS.
