# Release 1.5 — P0-4 Architecture & Product Design: Recommendation Engine

**Status: backend shipped (2026-07-22), frontend pending.** This
document is kept as the original design proposal; it is not fully
up to date with what actually shipped. Differences from the plan below:

- **v1 recommendation types shipped: `FOLLOW_UP` and
  `CHECK_PENDING_TASKS` only** — not the full 7-type list this document
  originally scoped (`SCHEDULE_MEETING`, `UPDATE_CONTACT`, `READ_NOTES`,
  `REVIEW_RELATIONSHIP`, `SEND_WHATSAPP` were deliberately deferred: each
  either needed fabricated message content, a compound condition not
  itself a single P0-3 signal, or both — narrowed further than approved
  to keep every shipped recommendation traceable to exactly one signal,
  per the "no speculative capabilities" principle). See
  `contacts/recommendations.py`'s own docstring for the exact reasoning.
- **Execution target naming**: the shipped `execution_target` values are
  literal Tool Registry names (`"create_task"`), not the
  `"task.create"`-style dotted strings sketched in §6/§9 below.
- **Endpoint path matches this proposal exactly**:
  `POST /contacts/{contact_id}/recommendations/{recommendation_id}/execute`.
- **Frontend not started** — no `ActionWorkflowControl` integration on
  `/contatos/[id]` yet; §10/§17/§19's frontend estimates remain proposed,
  not delivered.

Original document follows, unedited below this point.

## One correction before anything else

The brief's execution flow says `Recommendation → User confirms →
Planner → Tool → Audit Log`. I looked at what "Planner" actually is in
this codebase (`orchestrator/planning.py`) before designing around it,
and it is the wrong reuse target — routing through it would violate this
same brief's own rule ("LLM does NOT decide... does NOT execute").

`orchestrator.planning.CognitivePlanner` exists to interpret an
**ambiguous natural-language message** via one LLM call (`create_plan`)
and decide how many steps it needs and which agent handles each — its
own `Plan.confidence` field is explicitly documented as "how confident
the planner is that this decomposition... matches what the user needs,"
sourced from "the model's own self-reported confidence." A P0-4
recommendation is the opposite case: fully determined already (P0-3
already knows the exact signal, the exact tier, the exact suggested
action) — there is nothing ambiguous left for an LLM to plan. Sending a
known, confirmed action through the Cognitive Planner would mean asking
an LLM to re-decide something already decided deterministically, and
would import an LLM confidence score exactly where this brief says none
may exist.

**What actually should sit at that step is the Tool Registry**
(`agents/tools/base.py::Tool`), specifically `Tool.run(context,
arguments)` — a plain async function call, no LLM involved, already
used today by the executor for agent-initiated calls but equally
callable directly once both the tool name and its arguments are already
known (which they always are for a P0-4 recommendation). This is a
smaller, more honest reuse than either inventing something new or
stretching the Planner to a job it isn't built for. The rest of this
document is written around that correction; flagging it for your
explicit sign-off alongside the rest of the design.

---

## 1. Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │              RAW DATA (unchanged)             │
                    │  Messages · Notes · Tasks · CalendarEvent ·   │
                    │  Contact.preferences/summary (memory)         │
                    └───────────────────┬───────────────────────────┘
                                        │  (already loaded by
                                        │   get_contact_workspace,
                                        │   zero new queries)
                    ┌───────────────────▼───────────────────────────┐
                    │       SIGNALS + INSIGHTS  —  P0-3, UNCHANGED    │
                    │  contacts/intelligence.py:                     │
                    │  compute_signals → Signal[]                   │
                    │  relationship_tier, priority_score,            │
                    │  suggested_next_action                         │
                    └───────────────────┬───────────────────────────┘
                                        │  (P0-4 reads this output;
                                        │   never recomputes it)
                    ┌───────────────────▼───────────────────────────┐
                    │         RECOMMENDATIONS  —  P0-4, NEW           │
                    │  contacts/recommendations.py (pure function,   │
                    │  same style as intelligence.py):               │
                    │  build_recommendations(contact, signals,       │
                    │    tier, score, suggested_action)              │
                    │    → Recommendation[]                          │
                    └───────────────────┬───────────────────────────┘
                                        │
                    ┌───────────────────▼───────────────────────────┐
                    │              CONFIRMATION  —  P0-4, NEW         │
                    │  Reuses lib/actions.ts's existing               │
                    │  CLASSIFICATION (SAFE_AUTOMATIC /                │
                    │  REQUIRES_CONFIRMATION / MANUAL_ONLY) and       │
                    │  ActionPreview — no new confirmation UX         │
                    └───────────────────┬───────────────────────────┘
                                        │
                    ┌───────────────────▼───────────────────────────┐
                    │               EXECUTION  —  P0-4, NEW           │
                    │  Two lanes, both already existing primitives:  │
                    │  (a) direct REST call (PATCH /tasks/{id},      │
                    │      POST /tasks, POST /calendar) — same as    │
                    │      Action Center today                       │
                    │  (b) Tool Registry direct call                 │
                    │      (send_whatsapp_message, no LLM) — new     │
                    │      for a human-confirmed, non-conversational │
                    │      trigger, but the Tool itself is not new    │
                    └───────────────────┬───────────────────────────┘
                                        │
                    ┌───────────────────▼───────────────────────────┐
                    │                 AUDIT  —  P0-4, extends P4      │
                    │  POST /admin/actions/log (unchanged endpoint,  │
                    │  extended payload) → existing Timeline          │
                    └─────────────────────────────────────────────────┘
```

Nothing left of the "Signals + Insights" box changes. Everything right
of it is new, and every new box reuses an existing mechanism rather than
inventing one, per the brief's own rule.

## 2. Recommendation lifecycle

```
1. Contact Workspace request (or, later, the priority-ranking view)
   calls get_contact_workspace(), which already computes Signal[],
   tier, score, suggested_next_action (P0-3, unchanged).
2. build_recommendations(...) (new, pure) maps that output to zero or
   more Recommendation objects -- one per actionable signal, using a
   fixed signal→type table (§ Recommendation Types).
3. Recommendations are attached to the existing (currently always-[])
   `recommendations` field of the workspace response -- no second
   endpoint for the single-contact case.
4. Frontend renders each Recommendation via the existing
   ActionWorkflowControl (new props, no new component tree) with its
   classification-appropriate 1- or 2-click flow.
5. User confirms (or the 1-click case fires immediately, same as today).
6. Execution: a thin new endpoint (`POST /contacts/recommendations/{id}/
   execute` or reuse of the existing per-resource endpoint directly from
   the frontend, see § API proposal) performs the confirmed write via
   REST or Tool Registry (§1).
7. POST /admin/actions/log records the outcome, same as every existing
   Action Center workflow.
8. Recommendation is never "dismissed" as stored state -- like a
   Signal, it is a live, recomputed view. If the user acts on it (e.g.
   completes the task), the next read simply no longer produces that
   Recommendation, because the Signal that caused it no longer fires.
9. `expires_at` (schema field, § Recommendation schema) is a display
   hint only ("this framing is X hours old, refresh before trusting it
   verbatim") -- it does not gate whether the action can still execute;
   the execution endpoint always re-validates against live data before
   writing (see § Risks, staleness).
```

## 3. Data flow

```
GET /contacts/{id}/workspace
  └─ get_contact_workspace() [P0-2, unchanged: 6 queries]
       ├─ compute_signals(...) [P0-3, unchanged, in-memory]
       ├─ relationship_tier/priority_score/suggested_next_action [P0-3]
       └─ build_recommendations(contact, signals, tier, score) [P0-4, NEW, in-memory]
            └─ returns list[Recommendation] -- zero additional queries

POST /contacts/{contact_id}/recommendations/{recommendation_id}/execute [P0-4, NEW]
  ├─ re-fetch contact + re-run compute_signals (cheap: same 6 queries
  │   get_contact_workspace already does) to confirm the recommendation
  │   is still valid (staleness guard, § Risks)
  ├─ re-derive the same Recommendation deterministically from the same
  │   recommendation_id (never trust a client-supplied payload verbatim
  │   for anything that writes data -- see § Risks)
  ├─ dispatch to execution lane (a) REST-equivalent internal call or
  │   (b) Tool.run(context, arguments) -- both already-tested code paths
  └─ POST /admin/actions/log [unchanged endpoint, extended payload]
```

No new repository, no new query pattern beyond what P0-2/P0-3 already
run. The only genuinely new I/O is the audit log write, already existing.

## 4. Sequence diagrams

**Confirmed execution (REQUIRES_CONFIRMATION, e.g. FOLLOW_UP):**

```
User          Frontend               Backend                          Audit
 │  opens        │                       │                                │
 │  Contact ────►│ GET /contacts/{id}/workspace                          │
 │  Workspace    │──────────────────────►│ compute_signals + build_recs   │
 │               │◄──────────────────────│ { recommendations: [...] }     │
 │  sees "Follow-up" card, clicks once   │                                │
 │──────────────►│ show ActionPreview (existing component, no new logic) │
 │  confirms 2nd click                    │                                │
 │──────────────►│ POST .../recommendations/{id}/execute                 │
 │               │──────────────────────►│ re-derive Recommendation        │
 │               │                       │ dispatch → POST /tasks (existing)│
 │               │                       │──────────────────────────────►│ record_log()
 │               │◄──────────────────────│ { ok: true, task_id }          │
 │◄──────────────│ toast: done            │                                │
```

**SAFE_AUTOMATIC (e.g. mark a suggested task complete):**
Identical, minus the ActionPreview step — one click, same as today's
Action Center SAFE_AUTOMATIC kinds.

**MANUAL_ONLY (e.g. REVIEW_RELATIONSHIP, CALL_CLIENT):**
No execute call at all — the card is a link, same `manualOnlyAction`
shape `OperatorInsight` already has.

## 5. API proposal

- `GET /contacts/{id}/workspace` — **unchanged path**, `recommendations`
  field goes from always-`[]` to a real, deterministic list. No version
  bump needed (empty array → populated array is additive for any
  reasonable client, and the only client today, `/contatos/[id]`,
  already iterates it).
- `POST /contacts/{contact_id}/recommendations/{recommendation_id}/execute`
  — **new**, the only new endpoint this phase would add. Body: none
  required (the id round-trips everything needed; server re-derives,
  never trusts a client-echoed payload for the write itself — § Risks).
  Response: `{ ok: bool, result: <same shape the underlying endpoint
  already returns> }`.
- `GET /contacts/priority` — **unchanged**, from P0-3. Whether it also
  gains a `top_recommendation` field per contact is an open question,
  deferred to § Incremental implementation plan (not needed for v1).

No new router file: both endpoints belong in `api/contact_workspace.py`,
the same module P0-2/P0-3 already extended twice for exactly this reason
(one cohesive contact-facing surface, not a new one per phase).

## 6. Recommendation schema

```python
@dataclass(frozen=True)
class Recommendation:
    id: str                     # deterministic, e.g. f"{contact_id}-{signal.code}"
                                 # -- not a random UUID, so it's stable across
                                 # requests and re-derivable server-side (§3)
    type: str                   # fixed vocabulary, see § Recommendation types
    priority: str                # "urgent" | "attention" | "info" -- reuses
                                 # Signal.severity verbatim, no new scale
    confidence: int              # 95 | 65 | 35 -- reuses operator.ts's fixed
                                 # tiers verbatim, no new scale (§ Confidence)
    explanation: str             # one sentence -- reuses Signal.reason or
                                 # suggested_next_action verbatim
    reasoning: list[str]         # the literal supporting_signals' reasons,
                                 # bulleted -- never a separate LLM-authored
                                 # narrative (§ Explanation model)
    supporting_signals: list[str]  # Signal.code values, e.g.
                                 # ["relationship_stale", "overdue_commitment"]
    confirmation_required: bool  # derived from classification (§ Confirmation)
    execution_target: str | None # e.g. "task.create", "calendar.create",
                                 # "whatsapp.send" -- None for MANUAL_ONLY
    execution_payload: dict | None  # draft content shown in ActionPreview;
                                 # NEVER the source of truth at execute time
                                 # (server re-derives, § Risks)
    created_at: datetime         # when this read computed it (= request time)
    expires_at: datetime | None  # created_at + a short, configurable TTL
                                 # (display hint only, § lifecycle step 9)
```

Every field is either copied verbatim from a P0-3 output or derived by a
fixed, documented rule from it — nothing here is computed independently
of Signals.

## 7. Confidence model

Reused verbatim from `operator.ts` — **zero new scale**:

| Signal.severity | Recommendation.confidence | Recommendation.priority |
|---|---|---|
| urgent | 95 | urgent |
| attention | 65 | attention |
| info | never becomes a Recommendation (§ Recommendation types) | — |

Confidence answers "how sure is the *rule* that fired," not "how sure is
an AI this is a good idea" — same distinction `AI_OPERATOR.md` already
draws. No LLM is ever consulted for this number, and no continuous score
(e.g. 87.3) is ever fabricated in its place.

## 8. Explanation model

`explanation` is always `Signal.reason` (or, when a recommendation
aggregates multiple signals, `suggested_next_action`'s already-computed
top-priority text) — never independently generated. `reasoning` is the
literal bulleted list of every supporting signal's own `reason` string.
Worked example matching the brief's own format:

```
Recommended: FOLLOW_UP
Why?
  • Last conversation 21 days ago (relationship_stale)
  • 1 pending task (overdue_commitment is NOT present here -- this
    task is not overdue, just open; if it doesn't fire that risk
    signal, it must not appear as a reason)
  • Relationship tier: cooling
```

An optional LLM pass may rephrase this into more natural prose (e.g.
"It's been three weeks since you last talked, and there's still an open
item") but the bullet list above is always available, unedited, as the
literal ground truth — the LLM output is additive framing, never a
replacement, same as P0-3's `ai_summary`.

## 9. Planner integration

**Corrected per the note at the top of this document**: no integration
with `orchestrator.planning.CognitivePlanner`/`CognitivePipeline`. That
component's job (LLM-driven interpretation of ambiguous natural-language
requests, with its own self-reported LLM confidence) has no role once a
Recommendation is already fully determined and confirmed.

The actual reuse is the **Tool Registry** (`agents/tools/base.py`):
for execution kinds where an existing REST endpoint already does the
job (task/event creation, both already used by the Action Center),
that's the execution path, unchanged. For `SEND_WHATSAPP` specifically
— the one recommendation type with no existing REST surface — the
execute endpoint calls `send_whatsapp_tool.run(context, {"to":...,
"message":...})` directly, server-side, with **no LLM call** in that
path at all. This is the smallest possible new surface: one existing
Tool, invoked the same way the executor already invokes it, just
triggered by a confirmed human click instead of an agent's own
tool-selection step.

## 10. Action Center integration

**Yes — the Action Center should be the visual surface**, for contact-
scoped recommendations shown on the Contact Workspace page specifically.
Reasons:
- `ActionWorkflowControl.tsx` already renders exactly this shape
  (label, classification, 1/2-click, `ActionPreview`) — reusing it means
  zero new frontend component tree for the *card* itself, only new props
  and a new `kind` union member or two (`send_whatsapp` alongside the
  existing `complete_task`/`create_followup_task`/`schedule_time`).
- `computeAutomationScore` and the existing Timeline integration
  (`buildActionCenterEvent`) already generalize to any `admin:action.*`
  log source — a contact-scoped execution logs under
  `admin:action.contact_recommendation.<type>` and shows up for free.
- The dedicated `/admin/action-center` page stays the *admin-wide* queue
  (goals/tasks/jobs); contact recommendations render inline on
  `/contatos/[id]` using the same control, not by cramming a
  contact-scoped concept into the admin-wide page. A future aggregated
  "recommendations across every contact" view (§ open question,
  Incremental plan) would be a *second* place the same control renders,
  not a second implementation of it.

## 11. Audit strategy

Extends `POST /admin/actions/log` (unchanged endpoint) — the payload for
a contact recommendation adds:

```json
{
  "action_type": "contact_recommendation.follow_up",
  "recommendation_title": "Send follow-up",
  "result": "success",
  "detail": null,
  "related_entities": ["contact:42"],
  "supporting_signals": ["relationship_stale"],
  "recommendation_id": "42-relationship_stale"
}
```

`related_entities`/`detail`/`estimated_minutes` already exist on
`ActionLogCreate` — `supporting_signals`/`recommendation_id` are the
only new fields, both plain strings/lists, no new table. Confirmation
(who clicked, when) is implicit in the log entry's own `created_at` and
the fact it exists at all — same as every existing Action Center entry.

## 12. Performance analysis

- Single-contact case: **zero additional queries.** `build_recommendations`
  is a pure function over the `Signal[]`/tier/score `get_contact_workspace`
  already computed — no new repository call, no new table read.
- Execution endpoint: re-runs the same 6 queries `get_contact_workspace`
  already runs (to re-derive and validate, § Risks) plus whatever the
  underlying write already costs (1 query, unchanged from today's
  `PATCH /tasks/{id}` etc.), plus 1 audit-log write. No N+1: one
  recommendation execution is one contact, never a loop over contacts.
- No duplicated loading: the frontend continues to make exactly one
  request (`GET /contacts/{id}/workspace`) to render both the existing
  boxes and the new recommendation cards — never a second fetch for
  recommendations specifically.

## 13. Risks

- **Staleness between "recommended" and "confirmed."** A recommendation
  computed at request time could be stale by the time the user clicks
  confirm seconds/minutes later (e.g. someone else already completed the
  task). Mitigation: the execute endpoint always re-derives the
  Recommendation from live data before acting (§3) and returns a clear
  "no longer applicable" result rather than blindly trusting the
  client's cached payload — the same principle P0-2/P0-3 already applied
  (never trust a client-supplied fact for a write).
- **Recommendation ID collisions.** Deterministic IDs
  (`f"{contact_id}-{signal.code}"`) assume at most one recommendation per
  signal code per contact — true today (§ schema), but would need a
  documented tie-break if a future signal ever needs to produce more
  than one recommendation of the same code (none do yet).
- **SEND_WHATSAPP's execution lane is genuinely new surface**, not a
  pure reuse — it's the one place this phase adds a server-side call
  that didn't have an HTTP-reachable equivalent before. Small, but worth
  naming as the one non-trivial addition rather than folding it silently
  into "just like the others."
- **CALL_CLIENT / REVIEW_PORTFOLIO / PREPARE_PROPOSAL have no backing
  data model in this system today** (see § Recommendation types) — risk
  of the type vocabulary implying capability that doesn't exist. Flagged
  explicitly rather than silently included.

## 14. Alternatives considered

| Alternative | Verdict |
|---|---|
| Route execution through `CognitivePlanner`/`CognitivePipeline` (as literally proposed) | Rejected — reintroduces LLM-decided confidence/execution, violating this brief's own rule (§ correction at top) |
| A dedicated `recommendations` table, computed by a background job | Rejected for v1 — recommendations are cheap to recompute live (zero extra queries); persisting them would need a staleness/invalidation strategy for no benefit yet. Revisit only if the cross-contact aggregated view (§ Incremental plan) proves too slow computed live at scale |
| A new, separate confirmation UI distinct from the Action Center | Rejected — `ActionWorkflowControl` already does exactly this job; a second implementation would violate "no new recommendation engine" |
| Let the LLM freely decide priority/confidence per recommendation | Rejected outright — directly contradicts the brief |

## 15. Migration requirements

**None.** No new table, no new column. `Recommendation` is a computed,
never-persisted shape (dataclass, same as P0-3's `Signal`).

## 16. Testing strategy

Mirrors P0-3's own approach:
- Unit (no DB): `build_recommendations` given a fixed `Signal[]`/tier/
  score always produces the same `Recommendation[]` — one test per
  recommendation type, plus a test that an `info`-severity-only signal
  set produces zero recommendations (never fabricates urgency).
- Integration: `GET /contacts/{id}/workspace`'s `recommendations` field
  reflects live signals (extends `test_contact_workspace.py`, same
  pattern used for `relationship_status`).
- Integration: `POST .../execute` — confirms the underlying write
  happens, confirms the audit log entry is created with the right
  `supporting_signals`, confirms a staleness case (signal no longer
  fires) returns a clean "no longer applicable" result rather than
  executing a stale action anyway.

## 17. Incremental implementation plan

1. `contacts/recommendations.py` (pure module) + full unit tests —
   reviewable independent of any endpoint, like `intelligence.py` was.
2. Wire into `get_contact_workspace`'s `recommendations` field — a
   null-array→populated-array change only, same "smallest safe step"
   P0-3 used for its own two fields.
3. `POST /contacts/{id}/recommendations/{id}/execute` + integration
   tests.
4. Frontend: extend `ActionWorkflowControl` usage on `/contatos/[id]`
   to render the new cards — no new component tree.
5. Full validation pipeline, same rigor as P0-2/P0-3 (every result
   verified from log content).
6. Certification + explicit approval before any P0-4.1 (cross-contact
   aggregated recommendations view, if approved as a follow-up).

## 18. Estimated complexity

Comparable to P0-3, slightly smaller: P0-3 introduced a new module plus
two endpoints plus repository changes; P0-4 introduces one new module,
one new endpoint, and zero repository changes (nothing new to query).
Medium complexity, low risk — every execution lane is an already-tested
existing code path.

## 19. Estimated number of files

- New: `backend/contacts/recommendations.py`,
  `backend/tests/test_contact_recommendations.py` (2)
- Modified: `backend/api/contact_workspace.py` (new endpoint + wiring),
  `backend/admin/schemas.py` (2 new optional fields on `ActionLogCreate`),
  `frontend/app/(dashboard)/contatos/[id]/page.tsx`,
  `frontend/lib/actions.ts` (new action kind(s)),
  `frontend/tests/ContactWorkspacePage.test.tsx` (5)

Total: ~7 files touched, in line with P0-2/P0-3's own size.

## 20. Go / No-Go recommendation

**Go**, conditional on two explicit decisions from you:

1. **Confirm the Planner correction** (§ top of document) — proceed with
   direct REST / Tool Registry execution, not `CognitivePlanner`.
2. **Confirm the recommendation-type scope for v1** — recommend
   shipping `FOLLOW_UP`, `SCHEDULE_MEETING`, `UPDATE_CONTACT`,
   `CHECK_PENDING_TASKS`, `READ_NOTES`, `REVIEW_RELATIONSHIP` (all
   backed by real data/endpoints today), `SEND_WHATSAPP` (backed by an
   existing Tool, one new thin endpoint), and deferring `CALL_CLIENT`,
   `REVIEW_PORTFOLIO`, `PREPARE_PROPOSAL` — none of which this system
   has any underlying data for (no call log, no portfolio/investment
   domain, no proposal concept exist anywhere in this codebase's models
   today) — until/unless that data model exists.

## Recommendation types — full documentation

| Type | Backed by (P0-3 signal) | Execution today | Status |
|---|---|---|---|
| FOLLOW_UP | no_reply_to_inbound, relationship_stale | POST /tasks (existing) | Ready |
| SCHEDULE_MEETING | relationship_stale, upcoming_meeting_prepared (inverse) | POST /calendar (existing) | Ready |
| UPDATE_CONTACT | no_interaction_ever, stale categories/tags | PATCH /contacts/{id} (existing, generic CRUD) | Ready |
| CHECK_PENDING_TASKS | overdue_commitment | Link only (MANUAL_ONLY) — current_state.open_tasks already shows these | Ready |
| READ_NOTES | (informational, tied to important_notes) | Link only (MANUAL_ONLY) | Ready |
| REVIEW_RELATIONSHIP | any tier below healthy | Link only (MANUAL_ONLY) — opens the Contact Workspace itself | Ready |
| SEND_WHATSAPP | relationship_at_risk, no_reply_to_inbound | New thin endpoint calling the existing send_whatsapp_message Tool directly (no LLM) | Ready, smallest new surface |
| CALL_CLIENT | — | — | **Not supported** — no call log/data model exists in this system |
| REVIEW_PORTFOLIO | — | — | **Not supported** — no portfolio/investment domain exists in this system |
| PREPARE_PROPOSAL | — | — | **Not supported** — no proposal/sales domain exists in this system |

## User experience — three surfaces

1. **Contact Workspace** (`/contatos/[id]`) — in scope for this phase.
   Recommendation cards render inline where `recommendations: []`
   already has a slot, using `ActionWorkflowControl`, scoped to this one
   relationship only.
2. **Dashboard** (aggregated, across every contact) — explicitly **not**
   built this phase (§ Incremental implementation plan step 6+). Design
   note only: it would consume `GET /contacts/priority` (already exists,
   P0-3) the same way `/admin/action-center` consumes goals/tasks/jobs
   today — no new data source, just a second rendering surface for the
   same `Recommendation` shape.
3. **WhatsApp** (recommendations delivered/actioned via chat) — **future,
   no design commitment here.** Flagging one real tension for whoever
   picks this up later: WhatsApp delivery would need the *conversational*
   confirmation pattern (`CognitivePipeline`'s "confirma se é isso mesmo?"),
   which is a different confirmation mechanic than the dashboard's
   two-click `ActionWorkflowControl` — reconciling those two patterns is
   real design work, not assumed solved by this document.

---

Waiting for your approval — specifically on the Planner correction and
the v1 recommendation-type scope — before any implementation, endpoint,
or migration is created.
