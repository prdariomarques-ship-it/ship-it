# Contact Intelligence — P0-3 Architecture Proposal

**Status: design only.** Nothing in this document has been implemented.
No migration, endpoint, or frontend component exists yet. This is the
document P0-2's checkpoint (`RELEASE_1_5_P0_2_CHECKPOINT.md`) asked for
before any P0-3 code is written.

## Grounding: what already exists

Two precedents in this codebase already solve pieces of this problem, and
this proposal is a composition of both — not a new system next to them.

1. **`backend/goals/scoring.py`** — deterministic, DB-session-independent
   priority scoring for goals. A pure function over fixed weight tables
   (`_PRIORITY_WEIGHT`, `_MAX_DEADLINE_BONUS`, `_DEADLINE_HORIZON_DAYS`),
   unit-tested without touching a database, consumed by
   `goals/service.py::ready_goals` (`ready.sort(key=priority_score,
   reverse=True)`) and exposed via `GET /goals/ready?limit=`. This is the
   backend precedent for "deterministic scoring, not ML."
2. **`frontend/lib/operator.ts` + `frontend/lib/actions.ts`** (AI Operator
   Center / Action Center, `AI_OPERATOR.md` / `ACTION_CENTER.md`) — the
   existing "recommendation engine." Fixed confidence tiers (95/65/35, no
   continuous score), one plain rule per insight, a fixed action-kind
   vocabulary (`complete_task`, `create_followup_task`, `schedule_time`,
   ...), a three-way classification (`SAFE_AUTOMATIC` /
   `REQUIRES_CONFIRMATION` / `MANUAL_ONLY`), an `ActionPreview` before
   anything executes, and execution logged through the same
   `record_log()`/`event_bus.publish()` path everything else in
   `admin/router.py` already uses. This is the precedent for "how a
   recommendation becomes a safe, auditable action" — global (admin
   dashboard) today, not contact-scoped.

Everything below either reuses these two directly or extends them the
same way P0-2 extended the existing CRUD/repository pattern — no parallel
scoring engine, no parallel action/audit system.

## Architectural decision — RESOLVED (approved 2026-07-22)

**Intelligence and Action are separate responsibilities and must never be
merged into one module or one phase.**

- **P0-3 (Intelligence)** produces understanding only: relationship
  health, inactivity duration, follow-up urgency, pending items,
  conversation cadence, contact priority, and a plain-text
  `suggested_next_action`. No executable action, no command object, no
  side effect, no confirmation flow — `contacts/intelligence.py` never
  imports anything from `lib/actions.ts`'s domain, never writes to the
  database, never calls an endpoint.
- **P0-4 (Action)** consumes P0-3's output and is solely responsible for
  turning it into recommendations: explanation, confidence, confirmation,
  execution — reusing the existing Action Center / Planner infrastructure
  (`lib/actions.ts`, `ActionWorkflowControl`, `POST /admin/actions/log`),
  not a parallel one.
- All thresholds stay configurable (`Settings`, never a bare literal) —
  applies to every constant `contacts/intelligence.py` introduces,
  including the per-signal weights (a deliberate departure from
  `goals/scoring.py`'s own precedent of hardcoded weight constants: this is
  an explicit, current product decision for this feature specifically, not
  a claim that the older module is wrong).
- The performance objective is unchanged: zero additional database queries
  for the single-contact workspace; scoring runs entirely in memory over
  data `get_contact_workspace` already loads.
- The honest-data-model principle continues unchanged: never infer a fact
  the database doesn't support. The "missed meeting" signal stays excluded
  because `CalendarEvent` has no attendance column — this is not
  reconsidered by this decision.

This section supersedes the "Open decision" discussion below, kept
for its rationale.

## P0-4 status update (2026-07-22) — supersedes the open decision below

P0-4 has since been approved and its backend shipped. Kept here for
historical accuracy, but two things below turned out different from what
this document proposed — see `P0_4_RECOMMENDATIONS_ARCHITECTURE.md` for
the corrected design and its own "what shipped" note:

- **Execution reuses the Tool Registry** (`agents/tools/base.py::Tool`),
  not `lib/actions.ts`/`ActionWorkflowControl` as this section originally
  proposed. The Cognitive Planner was also explicitly evaluated and
  rejected as an execution path (it's LLM-driven interpretation of
  ambiguous requests; a confirmed recommendation is never ambiguous).
- **Only the backend shipped in this pass** —
  `contacts/recommendations.py`, the `recommendations` field on
  `GET /contacts/{id}/workspace`, and
  `POST /contacts/{id}/recommendations/{id}/execute`. The frontend
  (`ActionWorkflowControl` integration on `/contatos/[id]`) is not yet
  wired — the API returns real recommendations today with no UI
  consuming them yet.

## Open decision this document needs signed off before P0-4 starts

`api/contact_workspace.py`'s own docstring (written in P0-2) already
splits this territory in two:

> `relationship_status`/`suggested_next_action` are reserved for **P0-3**.
> `recommendations` (the executable list) is reserved for **P0-4**.

This proposal keeps that split. **P0-3 delivers the intelligence layer:
deterministic signals, a relationship-health tier, and a single
plain-language `suggested_next_action` string (informational, not
executable).** Turning those signals into a ranked `recommendations[]`
list with per-item action kind, classification, preview and one-click
execution is P0-4's job, reusing `lib/actions.ts`/`ActionWorkflowControl`
exactly as the Action Center already does for goals/tasks/jobs. Section 8
below explains why drawing the line here, not further, keeps each phase
independently shippable and testable. **This split is the one thing in
this document that most needs your explicit confirmation** — the
alternative (P0-3 also emits executable recommendations) is viable but
roughly doubles this phase's scope and couples it to the Action Center's
frontend machinery before the scoring model itself has been used in
production.

---

## 1. Objectives

Answer, for one contact and across all contacts, without a language
model in the hot path:

- Which clients require immediate attention?
- Which relationships are becoming cold?
- Which commitments are overdue?
- Which follow-ups make sense right now?
- Which risks are increasing?
- Which clients deserve priority today?

"Which opportunities exist" is scoped down in this phase (see §10) to
what's honestly derivable from data that exists today — this codebase
has no sales-pipeline/deal model, so "opportunity" here means relationship
opportunities (re-engagement, deepening), not commercial ones.

## 2. Functional scope

In scope:
- A deterministic scoring module computing, per contact: a relationship
  health tier, a set of named risk signals, a set of named opportunity
  signals, a priority score, and a single suggested next action string.
- Filling `summary.relationship_status` and `summary.suggested_next_action`
  in the existing `GET /contacts/{id}/workspace` response — no new field,
  no shape change, a null→value upgrade only.
- One new read endpoint returning contacts ranked by priority across the
  whole address book, mirroring `GET /goals/ready`.
- Optional, additive AI-generated explanation text (reusing
  `ContactMemoryService`'s existing LLM summary machinery) — never
  required, never able to change a score or a signal.

Out of scope (explicitly deferred):
- Executable recommendations (`recommendations[]`, action classification,
  execution, audit) — P0-4.
- Any new source feeding the timeline (Email, Calls, Documents, CRM) — a
  later phase; the scoring model is designed to accept new signal
  producers without a contract change (§6), but none are built here.
- Any persisted/cached snapshot table for intelligence — see §16.
- Proactive push notifications when a contact's tier changes — the event
  hook exists (§11) but nothing subscribes yet.

## 3. Non-functional requirements

- **Deterministic and reproducible.** Same inputs (contact row + its
  messages/notes/tasks/events + `now`) always produce the same tier,
  signals, and score. Every threshold lives in `Settings`
  (`utils/config.py`), never a bare literal in the scoring module —
  continuing the same principle P0-2's timeline-limit fix established.
- **Explainable.** Every signal that fires carries the literal condition
  that fired it (mirrors `OperatorInsight.reason`), never a bare number
  with no reason attached.
- **No new database queries for the single-contact case.** Scoring
  consumes data `get_contact_workspace` already loads; see §13.
- **Bounded cost for the cross-contact case.** The ranking endpoint uses
  aggregate SQL (COUNT/MAX/subqueries), never one query per contact.
- **AI-optional.** The service must produce a complete, correct result
  with zero LLM calls; an available LLM only adds a prose explanation
  layered on top, wrapped in the same try/except-and-log-warning pattern
  `get_contact_workspace` already uses for `ai_summary`/`memory`, so a
  degraded LLM/Qdrant never breaks scoring.
- **No parallel architecture.** New code lives as: one pure scoring
  module (mirrors `goals/scoring.py`), one or two new repository query
  methods (mirrors existing repositories), one router extension (same
  file as `contact_workspace.py`), zero new frameworks.

## 4. Inputs

Per contact, all already fetched by `get_contact_workspace` today — no
new query needed to add these as scoring inputs:

| Input | Source | Already loaded in P0-2? |
| --- | --- | --- |
| `Contact.last_interaction_at`, `.categories`, `.tags` | `ContactRepository.get` | Yes |
| Recent messages (direction, timestamps) | `MessageRepository.recent_for_contact` | Yes |
| Notes (pinned, created_at) | `NoteRepository.list` | Yes |
| Open tasks (status, priority, due_date) | `TaskRepository.list` | Yes |
| Upcoming + recent calendar events | `_fetch_upcoming_events` / `_fetch_recent_events` | Yes |

For the cross-contact ranking endpoint, inputs are aggregates rather than
full rows — see §11/§13.

## 5. Outputs

`summary.relationship_status` (was `null`) becomes a small typed object,
not a bare string — a bare enum with no breakdown would be exactly the
"black box" `AI_OPERATOR.md` explicitly rejects:

```json
"relationship_status": {
  "tier": "cooling",
  "score": 62,
  "signals": [
    {"code": "no_reply_to_inbound", "severity": "attention",
     "reason": "Last message was inbound 3 days ago with no reply since."}
  ]
}
```

`summary.suggested_next_action` (was `null`) stays a plain string — P0-3
does not attach an executable action to it (§8):

```json
"suggested_next_action": "Reply to the last message — it's been 3 days with no response."
```

New endpoint `GET /contacts/priority` returns an ordered array of the same
per-contact shape plus `contact_id`/`name` — see §12.

## 6. Intelligence model

A **signal** is the atomic unit: a named, boolean-or-tiered fact about one
contact, each produced by one small pure function, each independently
testable — the same granularity `operator.ts`'s per-insight rules use.
Signals compose into three derived views:

- **Relationship tier** (`healthy` / `cooling` / `cold` / `at_risk`) —
  derived primarily from recency (`last_interaction_at`) plus whether
  unresolved signals exist.
- **Priority score** (0–100, `goals/scoring.py`-style: fixed weights per
  signal, summed, no fabricated precision beyond what the weights
  justify) — used only for ranking, never shown as if it were a
  probability.
- **`suggested_next_action`** — a fixed template string picked by the
  single highest-severity signal present (ties broken by a fixed signal
  order, same determinism discipline as P0-2's timeline `(type, id)`
  tie-break), or a plain "no action needed" sentence when nothing fires.

A future signal source (e.g. an Email domain, once it exists) plugs in by
adding one function to the signal registry — the tier/score/action
derivation logic never needs to know how many sources exist, only that it
receives a `list[Signal]`.

## 7. Scoring strategy

```python
# contacts/intelligence.py (proposed, not created yet)

@dataclass(frozen=True)
class Signal:
    code: str            # e.g. "no_reply_to_inbound"
    kind: Literal["risk", "opportunity"]
    severity: Literal["urgent", "attention", "info"]
    weight: float         # fixed, from Settings-backed table
    reason: str           # literal condition that fired, human-readable

def compute_signals(
    contact: Contact,
    messages: list[Message],
    notes: list[Note],
    tasks: list[Task],
    events: list[CalendarEvent],
    *, now: datetime,
) -> list[Signal]: ...

def relationship_tier(contact: Contact, signals: list[Signal], *, now: datetime) -> str: ...

def priority_score(contact: Contact, signals: list[Signal]) -> float: ...

def suggested_next_action(signals: list[Signal]) -> str: ...
```

Every threshold (staleness days, overdue grace, weight per signal) is a
`Settings` field with a sensible default — same pattern as
`contact_workspace_timeline_limit` — never a bare literal in
`intelligence.py`. This directly continues the "no embedded business
values" correction applied to P0-2's timeline limit.

`priority_score` sums fixed per-signal weights (e.g. `at_risk` tier
contributes more than `cooling`; each firing risk signal adds a fixed
amount; opportunity signals subtract or add depending on whether "high
priority" here means "needs attention" — see §9/§10 for the exact
polarity). No goal-style deadline-proximity interpolation is proposed
initially (there's no single "deadline" concept for a relationship); if
recency-based interpolation proves useful once this ships, it is a
same-shaped addition to this module, not a rewrite.

## 8. Recommendation generation

**P0-3 produces `suggested_next_action` as a plain string only** — the
highest-severity signal's fixed template, no `action`/`classification`/
`targetId` attached. Rationale for stopping here (see the Open Decision
above for confirming this):

- `lib/actions.ts`'s classification (`SAFE_AUTOMATIC` /
  `REQUIRES_CONFIRMATION` / `MANUAL_ONLY`) and `ActionPreview` machinery
  are frontend-only today, wired to the Action Center's admin-wide data
  fetch, not to a per-contact one. Reusing them for contacts is real work
  (a `contact_id`-aware variant of `use-action-execution.ts`, new action
  kinds like `send_whatsapp_message` or `log_contact_note`) that deserves
  its own phase and its own validation, exactly the size P0-2 already
  was.
- Shipping the signal/score layer first lets it be exercised (and its
  thresholds tuned) against real data before any one-click execution
  path is built on top of it — cheaper to fix a mis-tuned threshold in a
  read-only field than after it is already driving executable actions.
- `api/contact_workspace.py`'s own P0-2 docstring already commits to this
  boundary; deviating from it silently would contradict a decision that
  document already made explicit.

If approved, P0-4 becomes: turn each `Signal` with `kind="risk"`/severity
above a threshold into an `OperatorAction`-shaped entry (reusing existing
action kinds where they already fit — `create_followup_task`,
`schedule_time` — adding contact-specific kinds only where nothing existing
fits), populate `recommendations[]`, and reuse
`ActionWorkflowControl.tsx`/`use-action-execution.ts`/`POST
/admin/actions/log` unchanged for execution and audit.

## 9. Risk model

Each risk signal is a small pure predicate over already-loaded data —
none require a new query:

| Signal | Condition | Severity |
| --- | --- | --- |
| `overdue_commitment` | Any open task (`status=PENDING`) with `due_date < now` | urgent |
| `no_reply_to_inbound` | Most recent message is `INBOUND` and older than `Settings.contact_reply_sla_hours` (default e.g. 24h) with no `OUTBOUND` message since | attention |
| `relationship_stale` | `last_interaction_at` older than `Settings.contact_stale_after_days` (default e.g. 14) | attention (escalates to urgent past `Settings.contact_at_risk_after_days`, default e.g. 45) |
| `no_interaction_ever` | `last_interaction_at is None` and contact has existed longer than a small grace window | info — a data-quality flag, not a relationship failure |

Deliberately not proposed: a "missed meeting" signal. `CalendarEvent` has
no attendance/status column (confirmed by reading `models/calendar.py`) —
inventing one from `starts_at < now` alone would conflate "meeting
happened" with "meeting was skipped," which is exactly the kind of
fabricated-precision the existing `operator.ts` deliberately avoids (see
its `assumed: true` handling for events with no `ends_at`). If this signal
matters, it needs an explicit attendance field first — a scope decision
for whoever owns that, not assumed here.

## 10. Opportunity model

Scoped to relationship opportunities only (§2) — this system has no deal/
pipeline model to source a commercial one from:

| Signal | Condition | Severity |
| --- | --- | --- |
| `reengagement_window` | A message arrived after a `relationship_stale` gap (contact reached back out after being cold) | info |
| `upcoming_meeting_prepared` | An upcoming calendar event exists with no open task tied to the same contact — a "nothing blocking, meeting is coming" positive signal | info |
| `healthy_and_quiet` | No risk signal fired at all and the contact has at least one prior interaction — mirrors `operator.ts`'s "everything quiet" opportunity insight, applied per-contact | info |

## 11. Data flow

Single-contact (extends the existing request, no new round trip):

```
GET /contacts/{id}/workspace
  -> get_contact_workspace()            [unchanged data loading]
  -> compute_signals(contact, messages, notes, open_tasks, timeline_events, now=...)
  -> relationship_tier(...), priority_score(...), suggested_next_action(...)
  -> summary.relationship_status / summary.suggested_next_action populated
```

Cross-contact (new endpoint, new aggregate queries, §13):

```
GET /contacts/priority?limit=N
  -> ContactRepository: contacts ordered by last_interaction_at (candidate set)
  -> TaskRepository (new): overdue-task counts grouped by contact_id
  -> MessageRepository (new): last message direction+timestamp per contact_id
  -> compute_signals()/priority_score() per candidate, in Python
  -> sort by priority_score desc (mirrors goals/service.py::ready_goals)
```

Optional, not required for P0-3 to ship: when a contact's tier crosses
into `at_risk`, publish `contacts.intelligence.risk_escalated` on the
existing `EventBus` (`events/bus.py`) — fire-and-forget, no new
subscriber required today; this is the hook a future proactive-alert
feature would subscribe to, following the exact same "publish now, wire a
consumer later" pattern already used for `whatsapp.message_received`.

## 12. API contract

No breaking change to `GET /contacts/{id}/workspace` — only two
previously-`null` fields gain real values, shape unchanged for
`relationship_status` object addition (still one key at that path,
frontend already renders it, currently as "Ainda não calculado.").

New:

```
GET /contacts/priority?limit=50
```

```json
[
  {
    "contact_id": 42,
    "name": "Ana Souza",
    "relationship_status": { "tier": "at_risk", "score": 88, "signals": [...] },
    "suggested_next_action": "Reply to the last message — it's been 6 days with no response."
  }
]
```

Mirrors `GET /goals/ready?limit=` exactly (query param name, bounds,
ranked-list shape) — same router file as `contact_workspace.py`, no new
router registered in `main.py` beyond what P0-2 already added.

## 13. Performance considerations

- **Single-contact path: zero new queries.** All scoring inputs are
  already loaded by `get_contact_workspace`; `compute_signals` is a pure
  in-memory function over that data.
- **Cross-contact path: bounded aggregate queries, not N+1.** Two new
  repository methods are proposed:
  - `TaskRepository.overdue_counts_by_contact(user_id) -> dict[int, int]`
    — one `GROUP BY contact_id` query.
  - `MessageRepository.last_message_by_contact(contact_ids) -> dict[int, tuple[direction, timestamp]]`
    — one query using a window function or `DISTINCT ON` (Postgres),
    scoped to a bounded candidate set (see next point), never the entire
    address book unfiltered.
  Candidate set is bounded before scoring: start from contacts with a
  non-null `last_interaction_at` within a generous lookback window (or the
  top-N by recency), the same "bounded candidate list, then rank in
  Python" shape `goals/service.py::ready_goals` already uses — never load
  every contact's full message history to rank them.
- **No caching layer proposed for P0-3.** At the address-book sizes this
  single-user system operates at (see `docs/CONTACTS.md` — a personal
  WhatsApp contact book, not a multi-tenant CRM), on-demand aggregate
  queries are expected to stay well under 100ms. If contact volume grows
  enough to matter, a periodic recompute-and-cache job (using the
  existing `jobs/` queue, same shape as `observation/scheduler.py`'s
  self-rescheduling tick) is the natural next step — explicitly not built
  now, since it would require a new table (§16 forbids that this phase).

## 14. Database impact

**None.** No column, table, or index is added by this phase. Every input
already exists (`Contact.last_interaction_at`, `Message.direction`,
`Task.due_date`/`.status`, `CalendarEvent.starts_at`, plus the
`contact_id` columns P0-2 already added to tasks/calendar). The two new
repository methods proposed in §13 are read-only aggregate queries against
existing columns; `Task.contact_id`/`CalendarEvent.contact_id` are already
indexed (P0-2's migration `2cc4e7d820a6`), so the `GROUP BY`/window-function
queries have an index to use without a new one.

## 15. Test strategy

Mirrors `tests/test_goals.py`'s approach to `goals/scoring.py` — unit
tests against the pure scoring functions directly, no DB, no HTTP client,
plus integration tests for the two endpoints:

- Unit (`tests/test_contact_intelligence.py`, no DB session):
  - Each signal predicate in isolation (fires / doesn't fire at the exact
    threshold boundary, same "barely overdue vs. very overdue" style
    already used in `test_goals.py`).
  - `relationship_tier` for every tier transition.
  - `priority_score` ordering (a contact with an overdue task outranks
    one with none, all else equal).
  - `suggested_next_action` tie-break determinism when two signals of
    equal severity fire (mirrors P0-2's equal-timestamp timeline test).
  - Zero signals (a perfectly healthy, quiet contact) — must not crash,
    must return a "no action needed" sentence, not an empty string.
- Integration (extends `tests/test_contact_workspace.py`):
  - `GET /contacts/{id}/workspace` for an empty-relationship contact:
    `relationship_status` is present and typed, not null; tier is a
    sensible default (not "at_risk" for a contact with no history at all
    — see `no_interaction_ever` being `info`, not `urgent`).
  - `GET /contacts/{id}/workspace` for an active, healthy contact: no risk
    signal fires, tier is `healthy`.
  - New: `tests/test_contact_priority.py` for `GET /contacts/priority`:
    ordering is descending by score, `limit` is honored, isolation between
    users' contacts holds (same discipline as P0-2's cross-contact
    isolation test), a contact with no signals still appears (never
    silently dropped from the ranking).

## 16. Migration requirements

**None for this phase.** Explicitly confirmed against §14: no new
column, table, or index. If a future caching/snapshot layer (§13) is
approved later, that becomes its own phase with its own migration —
not bundled into this one.

## 17. Rollout plan

1. Land `contacts/intelligence.py` (pure module) with full unit test
   coverage (§15) — mergeable and reviewable independent of any endpoint
   change, exactly like `goals/scoring.py` was.
2. Wire it into `get_contact_workspace` to populate
   `relationship_status`/`suggested_next_action` — a null→value change
   only; existing frontend rendering already has a slot for both fields,
   so this requires zero frontend change to ship safely (worth confirming
   with a quick manual check that the "Ainda não calculado" placeholder
   text is replaced correctly, not a functional risk).
3. Add `GET /contacts/priority` and its two supporting repository
   methods; integration tests per §15.
4. Optional, additive: wire `ContactMemoryService`'s existing LLM call
   pattern to generate one sentence of prose explaining the computed tier
   — same try/except-and-log-warning discipline `ai_summary` already
   uses, never blocking or replacing the deterministic result if the LLM
   call fails or is disabled.
5. Full validation pipeline (Ruff/Mypy/Pytest backend;
   ESLint/TypeScript/Vitest/Build frontend), same rigor as P0-2's
   certification — every result verified from log content directly, not
   from a wrapper exit code.
6. Certification report + explicit approval, same shape as
   `RELEASE_1_5_P0_2_CHECKPOINT.md`, before P0-4 (executable
   recommendations) begins.

---

**Waiting for explicit approval of this design — and specifically for a
decision on the P0-3/P0-4 boundary in the Open Decision section — before
any implementation, migration, endpoint, or frontend component is
created.**
