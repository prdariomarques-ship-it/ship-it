# AI Operator Center — Phase 1

The first thing the user sees on `/admin`: a single panel that continuously answers "what needs attention, what should I do next, what's most important today, what can be automated, what's at risk, what's an opportunity" — with every recommendation explaining *why* it exists.

## Deliberately not an LLM call

Every insight is a **deterministic rule over data the dashboard already fetches** (Goals, Tasks, Calendar, Jobs, CurrentContext) — not a prompt to a language model. Two reasons, both from the brief itself:

- **"No black-box AI. Every recommendation must explain why."** A rule like *"this task is overdue because `due_date < now`"* is inspectable, testable, and exactly reproducible. An LLM's reasoning for the same recommendation would not be, and would cost a real API call on every dashboard poll (5s/30s intervals) for no accuracy gain over a plain comparison.
- **Infrastructure frozen.** No new service, no new endpoint, no new call to an LLM provider — `frontend/lib/operator.ts` is a pure function, `buildOperatorInsights(input) → OperatorInsight[]`, unit-tested exactly like `goals/scoring.py` is on the backend (same idea: a deterministic, explainable scoring function, independent of any session/request state).

## The eight questions → eight categories

| Question from the brief | Category | Source data | Confidence |
| --- | --- | --- | --- |
| What needs attention? / What's most important today? | `highest_priority` | Top 3 `readyGoals` (already ranked by the backend's `priority_score`) | high |
| What should I do next? | `follow_up` | Goals `awaiting_approval` (need your decision) + tasks due within 48h | high |
| — | `missed_task` | Pending tasks with `due_date < now` | high |
| Calendar conflicts | `calendar_conflict` | Any two calendar events with overlapping `[starts_at, ends_at)` ranges | high (both times explicit) / medium (one end time assumed) |
| What risks exist? | `risk` | Failed jobs, WhatsApp disconnected, degraded Observation Engine sources, a goal with a deadline ≤3 days away but <50% progress | high (all four are direct facts, not inference) |
| What opportunities exist? | `opportunity` | A ready goal ≥80% complete; or "everything's quiet" (no failed job/awaiting-approval goal/overdue task) | medium (these are judgment calls, not facts — marked accordingly) |
| What can be automated? | `automatable` | Goals that already have `recurrence_interval_days` set; background jobs already running unattended | high — these are already-true facts about the system, not predictions |
| Recently observed changes | `recent_change` | Diff of `CurrentContext` dimension counts against the previous poll (goals/tasks/calendar/pending_work/conversations) | high (a count diff, not an inference) |

Two categories (`opportunity` items and the "assumed 30min duration" calendar-conflict case) are explicitly `medium` confidence, not `high` — they involve a judgment call or an assumption, and the UI never hides that distinction. This is the literal implementation of "AI Confidence" from the brief: a badge on every single insight, not one opaque aggregate score. `confidenceSummary()` additionally reports "N of M recommendations are high-confidence" as one honest aggregate line.

## Why the calendar-conflict logic discloses its own assumption

`CalendarEventRead.ends_at` is nullable — a real event can have no recorded end time. Rather than silently treating that as "instantaneous" (which would under-detect conflicts) or "all day" (which would over-detect them), `operator.ts` assumes a 30-minute duration — the same default most calendar UIs use — and **says so in the reason text** whenever that assumption is what triggered the finding, dropping the confidence to `medium` in that case only. This is the same "never a silent guess" discipline `orchestrator/context.py` and `observation/builder.py` already apply on the backend, ported to the one place on the frontend that now does its own inference.

## Architecture

```
frontend/lib/operator.ts                buildOperatorInsights(), confidenceSummary()
                                          — pure functions, no React, no fetch
frontend/hooks/use-previous.ts            usePrevious<T>() — one render behind,
                                          used only to diff CurrentContext snapshots
frontend/components/admin/
  AIOperatorCenter.tsx                    presentational: groups insights by category,
                                          renders severity + confidence badges + the
                                          "Por quê" (why) line + action buttons
app/admin/page.tsx                        wires it as the very first section (above
                                          Status dos sistemas), computes `insights` via
                                          useMemo from data already fetched by existing
                                          hooks (useReadyGoals, useGoalsAwaitingApproval,
                                          useTasks, useCalendarEvents, useJobsByStatus,
                                          useAdminObservation, useAdminWhatsApp)
```

**No new backend endpoint.** Every input to `buildOperatorInsights` was already being fetched by the dashboard (see `DASHBOARD_MVP.md`) — this phase is pure frontend composition over existing data, same principle the dashboard MVP itself established for "AI Suggested Actions."

## What this replaces

The former `SuggestedActionsPanel` (dashboard MVP) covered goal approvals, failed jobs, overdue tasks, and the next suggested goal — a subset of what the Operator Center now covers. Rather than keep two overlapping panels, `SuggestedActionsPanel.tsx` was deleted and its logic absorbed into `operator.ts`'s `follow_up`/`risk`/`missed_task`/`highest_priority` categories, with the same action buttons (Approve, Retry) preserved. One panel, not two competing ones — same anti-duplication principle the whole dashboard was built on.

## Testing

`frontend/tests/operator.test.ts` — 25 unit tests, one per rule and its negative case (e.g., "flags an overdue pending task" / "does not flag a completed task even if its due date is in the past"), covering every category, the calendar-conflict overlap math (including the assumed-duration and no-double-report cases), and `confidenceSummary`. Full frontend suite: 144/144 passing (119 pre-existing + 25 new). `tsc --noEmit`, `next lint`, and `next build` all clean.

## Known limitations

- **"What can be automated?" is grounded, not predictive.** It reports goals/jobs that are *already* automated (a real `recurrence_interval_days`, real running jobs) rather than inferring new automation candidates from behavioral patterns — there's no historical-pattern data to infer from yet (see `MEMORY_TIMELINE.md`, once built, for where that data would start accumulating).
- **"Recently observed changes" only diffs counts, not content.** `Metas: 3 → 4 (+1)` tells you something changed, not what. A richer diff (which goal, what field) would need CurrentContext to carry more than aggregate counts per dimension, or a real event-sourced timeline — see Phase 2.
- **Opportunity detection is intentionally conservative** (two rules: near-done goal, quiet system) rather than exhaustive — every rule added here is a permanent behavior users will come to expect; better to grow this list with real usage feedback than guess upfront.
