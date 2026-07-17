# Dario OS Operational Dashboard — MVP

A single screen (`/admin`, the existing Admin Dashboard's home page) that lets the owner operate Dario OS end to end: current world state, goals, tasks, calendar, WhatsApp status, system health, background jobs, and Cognitive Pipeline activity — with working actions (approve a goal, retry a failed job, cancel a pending job), not just read-only views.

**Scope discipline, as instructed**: no new backend services, providers, schedulers, repositories, or event buses. Exactly one new backend surface was added — `GET /api/admin/observation` — because `CurrentContext` (built weeks earlier as part of the Context Observation Engine) had no HTTP endpoint at all; everything else reuses endpoints that already existed before this milestone.

## The ten panels

| # | Panel | Backend source | New backend work |
| --- | --- | --- | --- |
| 1 | Current Context | `GET /api/admin/observation` | **New** — thin route over the existing `ContextObservationEngine` (see `docs/OBSERVATION_ENGINE.md`), builds on demand if nothing cached yet |
| 2 | Active Goals | `GET /api/goals/ready` | Fixed a real bug hit while seeding demo data — see `BUG_DISCOVERY_REPORT.md` |
| 3 | Today's Tasks | `GET /api/tasks` (client-side filter: pending, due today or overdue) | None |
| 4 | Calendar | `GET /api/calendar` (client-side filter: upcoming, sorted) | None |
| 5 | WhatsApp connection status | `GET /api/admin/whatsapp`, `GET /api/admin` | None |
| 6 | Recent Events timeline | `GET /api/admin/logs` (reuses the existing `LogViewer` component) | None |
| 7 | Pending Jobs | `GET /api/jobs?status=queued\|running` + existing `POST /api/admin/jobs/{id}/cancel` | None (first frontend UI to actually call the pre-existing P6 cancel/retry endpoints) |
| 8 | AI Suggested Actions | Composed client-side from: `GET /api/goals?status=awaiting_approval`, `GET /api/jobs?status=failed`, overdue tasks, and the top `ready_goals` entry — each with a working action button | None — pure composition of already-fetched data |
| 9 | System Health | `GET /api/admin/status` (existing `StatusCard` grid) | None |
| 10 | Cognitive Pipeline activity | `GET /api/admin/logs?source=cognitive_pipeline` | None |

## What's genuinely new

**Backend** (2 files touched, both minimal):
- `backend/admin/router.py` — `GET /observation`, ~20 lines, delegates entirely to `observation/engine.py` (already built, already tested).
- `backend/goals/scoring.py` — one defensive fix found during acceptance testing (see `BUG_DISCOVERY_REPORT.md`).

**Frontend** (all in the established `components/admin/` / `lib/admin-*` pattern — same design system, same react-query polling idiom, same loading/error/empty state components every other admin page already uses):
- `lib/admin-types.ts` — `CurrentContext`, `GoalRead`, `TaskRead`, `CalendarEventRead`, `JobRead` types (mirroring the backend schemas exactly, same convention as every other type in this file).
- `lib/admin-api.ts` — `useAdminObservation`, `useReadyGoals`, `useGoalsAwaitingApproval`, `useTasks`, `useCalendarEvents`, `useJobsByStatus` — same `useQuery` + `refetchInterval` shape as every existing hook (5s for anything live/actionable, 30s for the rest).
- Seven new presentational components: `CurrentContextPanel`, `GoalsPanel`, `TasksPanel`, `CalendarPanel`, `SuggestedActionsPanel`, `PendingJobsPanel`, `PipelineActivityPanel`.
- `app/admin/page.tsx` — rewritten to compose the existing System Health / Overview / real-time-charts sections (unchanged) with a new "Operação" section holding all ten panels, plus three `useMutation` calls (approve goal, retry job, cancel job) wired to toasts and query invalidation.

## Real-time behavior

Same polling idiom the existing admin dashboard already established (`docs/DASHBOARD.md`): no WebSocket, no new push mechanism — `useQuery({ refetchInterval })` at 5s for anything actionable/live (Current Context, WhatsApp, Pending Jobs) and 30s for slower-moving data (Goals, Tasks, Calendar, Logs). Consistent with the rest of the codebase's explicit "real-time means short-interval polling over REST, not a new transport" decision.

## Verification

- **Backend**: 875/875 tests pass (`pytest -q`), including 4 new tests for the observation endpoint and 1 new regression test for the goals-scoring bug. `ruff check` and `mypy --ignore-missing-imports` clean on every touched file.
- **Frontend**: 119/119 existing tests pass unmodified (`vitest run`), `tsc --noEmit` clean, `next lint` clean, `next build` succeeds (`/admin` compiles to 50.9kB, reasonable for the added functionality).
- **Product Acceptance Review**: full browser-driven walkthrough via Playwright — see `PRODUCT_ACCEPTANCE.md` for the panel-by-panel checklist, screenshots (`docs/screenshots/dashboard-mvp/`), known limitations, and readiness score (85% — construction complete, pending production deployment).

## What this is not

- Not a rebuild of the existing Sprint 4 admin dashboard (`docs/DASHBOARD.md`) — every one of its 12 pages (Agents, Tools, Executions, Memory, Google, WhatsApp, Users, Logs, Metrics, System, Settings, and the original overview) is untouched and still reachable from the sidebar; this milestone only extends the overview page (`/admin`) into the requested one-screen operational view.
- Not a new architectural layer — every panel is a read (or, for three actions, a write to an endpoint that already existed) through the exact same `apiFetch`/`useQuery` path every other admin page already uses.

## Remaining work

See `PRODUCT_ACCEPTANCE.md` — primarily: deploy the updated backend and frontend to production (the new endpoint and panels only exist in this session's code and in the isolated demo/dev instances used for screenshots).
