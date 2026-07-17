# Memory & Timeline — Phase 2

Transforms the raw `logs` audit trail into **operational memory** — organized by subject, explained, and curated — not a flat event log. Lives at `/admin/timeline`.

## The four questions

| Question | Where it's answered |
| --- | --- |
| What happened? | The eight grouped sections (below), each event with a plain-language `summary` |
| Why did it happen? | Every event's `reason` field — the literal condition that produced it |
| What changed? | The "O que mudou desde ontem?" / "desde meu último login?" quick-answer cards |
| What should I remember? | "Mudanças mais importantes" — the highest-`importance` events, not a re-dump of everything |

## Every event, in full

Per the brief's exact requirement, every `TimelineEvent` (`frontend/lib/timeline.ts`) carries:

`timestamp` · `actor` (`user` / `ai` / `system`) · `category` (one of the eight sections) · `summary` · `reason` · `relatedEntities` · `consequence` · `suggestedFollowUp` (when applicable) · `importance` (0-100, same tier-based honesty as `lib/operator.ts`'s confidence — see that file's "why three fixed numbers" for the underlying reasoning, reused here).

## Eight sections, not a flat list

| Section | Real source | Actor |
| --- | --- | --- |
| Conversas recentes | `GET /messages` — actual message content, not log lines | `system` (inbound) / `ai` (outbound) |
| Progresso de metas | `logs` where `source LIKE 'goal:%'` (`goals/events.py`) | `user` (explicit action) / `system` (automatic recurrence spawn) |
| Progresso de tarefas | `Task.created_at`/`updated_at` directly (no task event log exists — see Known Limitations) | `user` |
| Mudanças na agenda | `CalendarEvent.created_at`/`updated_at` directly (same limitation) | `user` |
| Atividade do WhatsApp | `logs` where `source LIKE 'whatsapp:%'`, `'webhook:whatsapp'`, or `'job:whatsapp.*'` | `system` (infra/queue) / `ai` (the auto-reply job specifically) |
| Decisões da IA | `logs` where `source = 'cognitive_pipeline'` — intent, priority, agents, confirmation state, all from the pipeline's own real payload | `ai` |
| Eventos do sistema | `logs` where `source LIKE 'admin:%'` (explicit dashboard actions) or any job not whatsapp-related | `user` (admin actions) / `system` (background jobs) |
| Observation Engine | `logs` where `source = 'job:observation.tick'` — **rolled up**, not listed raw (see below) | `system` |

Morning Activity isn't a ninth data source — it's a time-of-day slice (00:00–12:00 UTC) across whatever's already categorized above, shown only when viewing Today/Yesterday.

## The Observation Engine noise problem — found, and actually fixed this time

`docs/OBSERVATION_REVIEW.md` already flagged, as a known limitation, that `observation.tick`'s own job-lifecycle logging (two rows every few minutes) dominates the raw `recent_events` feed. Phase 2 is where that finally gets fixed — and building it surfaced a **second, more serious version of the same problem** that the architecture review didn't anticipate:

### Bug found during this phase: noise crowds out real events entirely, not just visually

The original design fetched "most recent 1000 logs, then filter tick noise out client-side." That's insufficient — with `observation.tick` writing 2 rows every 5 minutes (288/day in production; every 20s in the demo environment used to validate this), a 1000-row page fills up with nothing but tick activity within hours, pushing genuinely rare events (a goal created days ago, a job that failed once) **off the page entirely**, not just out of view. This was caught by direct testing during this phase, not assumed: a demo environment's goal-creation logs (ids 7–11) were completely absent from a 1000-row fetch whose oldest row was id 2006, because ~3000 tick rows had accumulated in between.

**Fix**: `GET /admin/logs` gained a new `exclude_source` param (`admin/router.py`) — filters *inside* the SQL query, before `limit` truncates anything, so the row budget is spent entirely on real content. The Timeline now issues two independent queries: one excluding `job:observation.tick` (the 1000-row budget for everything that matters), and one *only* fetching `job:observation.tick` with its own bounded sample (`TICK_SAMPLE_LIMIT = 800`) purely to answer "is the system still observing regularly" — never to enumerate every tick.

Covered by a backend regression test (`test_admin_logs_exclude_source_filters_before_limit_is_applied`) that specifically asserts a rare event survives being outnumbered 5-to-1 by a noisy source within a `limit=1`, and by direct verification against a real demo database where the bug was originally observed.

### Honest about sampling, even after the fix

Since the tick sample itself is bounded (800 rows), the rollup can't always report an exact count — if the sample came back *at* its limit, there may be more ticks beyond it that weren't fetched. `observationEngineRollup` labels the count as `"N+"` rather than `"N"` in that case (verified in `tests/timeline.test.ts`), the same "never claim more precision than the data supports" discipline used throughout this codebase (`goals/scoring.py`'s confidence tiers, `observation/models.py`'s `degraded_sources`).

## "What changed since X?" and "Most important changes"

`summarizeChanges(events, since, label)` — filters to events at or after `since`, counts them by section, and surfaces the top 5 by `importance`. Three instances on the page:

- **Desde ontem** — `since` = start of yesterday (a real calendar boundary, see `filterRange`).
- **Desde meu último login** — `since` = the previous value of `hooks/use-last-login.ts`'s client-side timestamp (see below). Shows "esta é sua primeira visita" instead of a summary when there's no previous value, rather than a confusing empty state.
- **Mudanças mais importantes** — `since` = the full 30-day base window, so this one surfaces the highest-importance events regardless of the active filter tab.

## Filters: Today / Yesterday / 7 Days / 30 Days / Everything

`filterRange(filter, now)` returns real `{since, until}` `Date` bounds — critically, **Yesterday is a calendar day** (`[start of yesterday, start of today)`), not "now minus 48 hours." A trailing-timedelta model (like `/admin/executions`'s existing `period` param already uses) genuinely cannot express that, which is why `/admin/logs` gained real `since`/`until` datetime params instead of another `period` enum. All five boundary cases are unit-tested precisely (`tests/timeline.test.ts::filterRange`).

The section list always operates on one shared 30-day fetch (`baseRange`); the active filter tab narrows *which* of those already-fetched events are displayed, client-side — avoiding a network round-trip on every tab click, and letting the "since yesterday"/"since last login" cards work correctly regardless of which tab happens to be selected.

## "Since my last login"

No backend session-history table exists, and creating one just for this would be new infrastructure this phase explicitly can't add. `hooks/use-last-login.ts` tracks it client-side instead: on mount, read the previously-stored timestamp (if any), then immediately overwrite it with now. Honest about what it actually measures — "the last time this browser opened the dashboard," not an audit-grade login record — which is exactly what a single-owner system needs and nothing more.

## Architecture

```
frontend/lib/timeline.ts                  buildTimelineEvents(), filterRange(),
                                            groupBySection(), morningActivity(),
                                            mostImportantChanges(), summarizeChanges()
                                            — pure functions, no React, no fetch
frontend/hooks/use-last-login.ts            client-side "previous visit" timestamp
frontend/components/admin/
  TimelineEventCard.tsx                     one event: actor icon, summary, why,
                                            consequence, related entities, follow-up
app/admin/timeline/page.tsx                 filters, quick-answer cards, morning
                                            activity, the eight sections
backend/admin/router.py                     + since/until/exclude_source on /admin/logs
                                            (the only backend change this phase needed)
```

Nav entry added as **"Timeline"**, deliberately not "Memory" — `/admin/memory` already exists (Sprint 4, vector/Qdrant embedding stats, a completely different concept). That existing entry was relabeled "Memory (vector)" to remove any ambiguity between the two.

## Testing

- `frontend/tests/timeline.test.ts` — 29 unit tests: every section's categorization rule, the calendar-day-vs-trailing-window distinction for all five filters, the observation-engine rollup (including the exact-vs-"N+" truncation-honesty case and "never rolls up a failure"), task/calendar "created vs updated" proxy logic (including the regression described below), morning-activity time bucketing, `mostImportantChanges` ordering, and `summarizeChanges`.
- `backend/tests/test_admin.py` — 2 new tests: `since`/`until` real date-range filtering, and `exclude_source` filtering *before* `limit` (the crowding-out regression guard).
- Full suite: **185/185 frontend**, **877/877 backend**. `tsc --noEmit`, `next lint`, `next build` all clean.
- Browser-verified (Playwright) against an isolated demo database seeded with real goals/tasks/calendar/messages/a failed job, confirmed against direct API calls before and after the `exclude_source` fix, and against the real accumulated `observation.tick` volume from a long-running demo session (3000+ log rows) — not a small, easy synthetic case.

## Bugs found during this phase (see also `BUG_DISCOVERY_REPORT.md` for Phase-1-era findings)

1. **`buildCalendarEvents` always treated `since === undefined` as "always show as created, never as updated"** — an actual logic bug caught by this phase's own test suite before it ever reached a screenshot. The "was this modified after creation" check had been conflated with "is a date filter active," so the "Everything" view (no `since`) silently could never show an "updated" event, no matter how obviously an event's `updated_at` had diverged from its `created_at`. Fixed by separating the two conditions; regression-tested.
2. **The `observation.tick` crowding-out bug** — see above, the more serious of the two, found only because this phase's browser validation used a demo database with real accumulated volume rather than a handful of freshly-seeded rows.

## Known limitations

- **Task Progress and Calendar Changes are `created_at`/`updated_at` proxies, not real event logs.** Unlike goals (which publish real lifecycle events via `goals/events.py`), no equivalent publisher exists for `Task` or `CalendarEvent` — so the Timeline can report *that* a calendar event changed (its `updated_at` moved) but not *what* field changed. Documented, not hidden: the event's own `reason` text says exactly this ("detalhe exato não registrado").
- **Outbound-message actor attribution is a simplification.** `Message.direction=outbound` is tagged `actor: "ai"` regardless of whether it was the Cognitive Pipeline's auto-reply or a manual send via the dashboard — the `Message` model alone can't distinguish the two without a deeper join against `logs`/`jobs` history that wasn't judged worth the complexity for this phase.
- **The Observation Engine rollup count is a bounded sample** (`TICK_SAMPLE_LIMIT = 800`), not a database-wide count — by design (see above), with the `"N+"` labeling making the limitation visible in the UI rather than silently approximate.
- **"Since my last login" is per-browser**, not a real session audit trail — acceptable for a single-owner system, same reasoning already applied to `AI_OPERATOR.md`'s dismiss/snooze/complete state.
