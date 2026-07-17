# Action Center — Phase 4

The AI stops only recommending and starts executing. Every recommendation the Operator Center or Daily Briefing surfaces now exposes a real, one-click **workflow** — not a bare button — that runs an already-existing endpoint end-to-end and records what happened. Lives at `/admin/action-center`, and the same workflow control is embedded directly on the Operator Center and Daily Briefing so users never have to leave those pages to act.

## Not a new execution engine

Every workflow calls an endpoint that already existed before this phase:

| Workflow | Real endpoint |
| --- | --- |
| Concluir tarefa | `PATCH /tasks/{id}` (`status: "done"`) |
| Adiar 1 dia | `PATCH /tasks/{id}` (`due_date: +1 day`) |
| Aprovar meta | `POST /goals/{id}/approve` |
| Tentar novamente (job) | `POST /admin/jobs/{id}/retry` |
| Criar tarefa de acompanhamento | `POST /tasks` |
| Agendar tempo para isso | `POST /calendar` |

The only net-new backend surface is `POST /admin/actions/log` — a thin wrapper over the same `record_log()`/`event_bus.publish()` pattern `admin_cancel_job`/`admin_retry_job` already used (see `backend/admin/router.py`). It performs no action itself; it only answers the one question the generic CRUD endpoints above can't: *why* did this write happen, and which recommendation caused it. A second small addition, `source_prefix` on `GET /admin/logs`, exists because every workflow kind logs under its own exact source (`admin:action.complete_task`, `admin:action.retry_job`, ...) — there's no single exact `source` value meaning "every action log," and the alternative (fetch broadly, filter client-side) would recreate the exact crowding-out bug Phase 2 already found and fixed for `observation.tick`.

## Workflows, not buttons

Per-instance the system shows a plain button; conceptually every action is a short, fixed, documented sequence (`WORKFLOW_STEPS` in `frontend/lib/actions.ts`):

- **Concluir tarefa** — Abrir tarefa → Marcar como concluída → Registrar execução
- **Adiar 1 dia** — Abrir tarefa → Adiar prazo em 1 dia → Registrar execução
- **Tentar novamente** — Abrir job → Reenviar para a fila → Registrar execução
- **Aprovar meta** — Revisar meta → Aprovar → Liberar para a fila de execução → Registrar execução
- **Criar tarefa de acompanhamento** — Revisar meta em risco → Criar tarefa de acompanhamento → Registrar execução
- **Agendar tempo para isso** — Sugerir horário disponível → Criar evento na agenda → Registrar execução

The last step of every one of these is always the same: an entry is written via `POST /admin/actions/log`, which is what makes it show up in the existing Timeline (see below) — "register execution" isn't a separate manual step, it's built into the workflow itself.

Steps are shown to the user (as a tooltip on one-click actions, inline in the confirmation panel for two-click ones) so the mental model is "the system is doing several things for me," not "I clicked an opaque button" — while the *interaction count* stays at the minimum the classification allows (see below). "Resolve overdue task" maps almost exactly onto the brief's own example: **Concluir tarefa** OR **Adiar 1 dia** are real OR-branches of the same task (`OperatorInsight.alternativeActions`), not two unrelated buttons.

## Classification: SAFE_AUTOMATIC / REQUIRES_CONFIRMATION / MANUAL_ONLY

One fixed classification per workflow kind (`CLASSIFICATION` in `lib/actions.ts`) — never a per-instance guess, same discipline as `lib/operator.ts`'s confidence tiers:

| Classification | Kinds | Interactions | Why |
| --- | --- | --- | --- |
| **SAFE_AUTOMATIC** | complete_task, reschedule_task, retry_job | 1 click | Internal-only, reversible (a task can be reopened, a due date re-adjusted, a job cancelled again) |
| **REQUIRES_CONFIRMATION** | approve_goal, create_followup_task, schedule_time | 2 clicks | Either unlocks real downstream automation (approving a goal — the goal system itself already requires this, see `goals/router.py`'s own "not automatically trusted to self-approve" comment) or creates a new record with system-guessed content (a task title/date, a calendar slot) that deserves a look before it's committed |
| **MANUAL_ONLY** | (none — always a link) | 0 (navigation only) | The fix genuinely requires a human: choosing which of two calendar events to keep, scanning a WhatsApp QR code on a physical device, investigating a degraded observation source, doing the real work behind a goal near completion |

**"If an action cannot be executed safely, explain why"** is satisfied literally: every `ActionPlan` carries a `classificationReason` string, shown on hover for automatic actions and inline for everything else — visible in the "Requer ação manual" section of the Action Center for every MANUAL_ONLY insight.

The second click of a REQUIRES_CONFIRMATION workflow opens *inline*, in the same card — no new screen, no form to fill in. For the two kinds that create a new record, the confirmation panel shows the exact draft content (`buildFollowupTaskDraft`/`buildScheduleTimeDraft` in `lib/actions.ts` — due today end-of-day for follow-up tasks, one hour from now for 30 minutes for scheduled time, same conservative-default discipline as the 30-minute assumed-duration rule already used for calendar-conflict detection) before it's ever sent.

## Action Preview — six fixed questions, answered before every confirmation

Every `ActionPlan` can produce an `ActionPreview` (`buildActionPreview()` in `lib/actions.ts`), one fixed template per action kind (`PREVIEW_TEMPLATE`) answering exactly the six questions the brief specified:

1. **O que vai acontecer** — one plain-language sentence.
2. **Afeta** — the concrete entity: the drafted new record's title for create actions, the insight's own title otherwise.
3. **Pode ser desfeito** — a boolean plus a rollback note. Deliberately *not* all `true`: **`approve_goal` is honestly marked non-reversible** — there is no "unapprove" endpoint, and the preview says so rather than implying every action is safely undoable.
4. **Tempo estimado** — always "instantâneo," because every action here is a synchronous HTTP call to an already-tested endpoint (`retry_job` is explicit that the call itself is instant even though the job's own reprocessing runs later, asynchronously).
5. **Efeitos colaterais** — a short fixed list per kind (e.g. `schedule_time` honestly discloses "nenhuma verificação automática de conflito de horário é feita" instead of implementing conflict detection that doesn't exist).
6. **Confiança de execução** — a fixed sentence, not a fabricated percentage: every kind here calls a stable, already-tested endpoint, so there's nothing to express as a numeric probability without inventing precision that doesn't exist.

Full panel for REQUIRES_CONFIRMATION (the second click *is* the review moment); for SAFE_AUTOMATIC the same facts are folded into the button's hover tooltip instead of forcing a second click — a mandatory preview step for an already-reversible, already-low-risk one-click action would contradict the "fewest possible interactions" principle these actions exist to satisfy.

## Execution history lives in the existing Timeline

No new history subsystem. `POST /admin/actions/log` writes to the same `logs` table every other admin action already uses; `frontend/lib/timeline.ts` gained one more source-prefix branch (`buildActionCenterEvent`, checked before the generic `admin:` handler) that turns each entry into a normal `TimelineEvent` — recommendation, selected action, timestamp, result, actor (`user`), related entities are all already fields on `TimelineEvent`, so nothing new had to be invented to display them. A failed execution renders with higher importance (65) than a success (40), same "a failure is more noteworthy than routine success" logic the Observation Engine rollup already uses for ticks.

## Measuring value — only from real executions

The Automation Score (`computeAutomationScore` in `lib/actions.ts`) is derived exclusively from real `admin:action.*` log entries plus one real-time count — never an estimate invented after the fact:

- **Ações concluídas hoje** — count of successful entries since local midnight (UTC).
- **Minutos economizados hoje** — sum of `estimated_minutes` *captured at the moment of execution* (the same fixed, documented per-category estimate `lib/operator.ts` already uses — Phase 4 doesn't invent a new estimate, it just totals the existing ones for actions that actually happened).
- **Operações manuais evitadas hoje** — equal to "ações concluídas" by construction: every logged action is, by design, a one-click (or two-click) replacement for what would otherwise be a multi-step manual operation (open a screen, find the record, edit it, save). Kept as a separate stat because it answers a different question, even though the number is always identical today — documented here rather than silently duplicated.
- **Confirmações pendentes** — a real-time count of currently-visible REQUIRES_CONFIRMATION insights, not a log-derived number.

## Architecture

```
backend/admin/router.py          POST /admin/actions/log (new)
                                  GET /admin/logs + source_prefix (new param)
backend/admin/schemas.py         ActionLogCreate / ActionLogRead

frontend/lib/actions.ts          classification, WORKFLOW_STEPS, planAction(),
                                  planAlternatives(), draft builders,
                                  computeAutomationScore(), parseActionLog()
                                  — pure functions, no React, no fetch
frontend/lib/operator.ts         OperatorAction extended: complete_task,
                                  reschedule_task, create_followup_task,
                                  schedule_time (+ optional draft);
                                  alternativeActions; manualOnlyAction
frontend/lib/timeline.ts         + buildActionCenterEvent() for admin:action.*
frontend/hooks/
  use-action-execution.ts        the one place that actually calls the
                                  existing endpoints, then logs the result
frontend/components/admin/
  ActionWorkflowControl.tsx      shared 1/2-click workflow control, used by
                                  AIOperatorCenter, BriefingRecommendationCard
                                  and the Action Center page
app/admin/action-center/page.tsx Pending / Aguardando confirmação / Em
                                  execução / Requer ação manual / Concluídas
                                  / Falhadas + Automation Score
```

## Testing

- `backend/tests/test_admin.py` — 6 new tests: `/admin/actions/log` success (level=info, payload persisted), failure (level=warning), retrievable via `/admin/logs`, requires auth, requires admin role; `source_prefix` filters before `limit` (the same crowding-out regression pattern as Phase 2's `exclude_source` test).
- `frontend/tests/operator.test.ts` — 7 new tests covering the new action/alternativeActions/manualOnlyAction fields on every affected category.
- `frontend/tests/actions.test.ts` — 19 new tests: classification for every kind, alternatives, draft builders (exact date math, never a silent guess), `buildActionPreview` (all six questions present, `approve_goal` honestly marked non-reversible, `open_related_item` returns `null`), `parseActionLog` (including "missing result defaults to nothing hidden, a failure is never silently dropped"), `computeAutomationScore` (today-only filtering, real minute totals, zero-entries case).
- Full suite: **231/231 frontend** (206 prior + 25 new), **883/883 backend** (877 prior + 6 new). `tsc --noEmit`, `next lint`, `next build` all clean.
- Browser-verified against the isolated demo environment (real seeded data: a failed job, three overdue tasks, three goals awaiting approval, WhatsApp disconnected): executed a real two-click REQUIRES_CONFIRMATION action (approve a goal — confirmed the Action Preview panel rendered all six questions with real content, including the honest "não pode ser desfeito" for approve_goal) and a real one-click SAFE_AUTOMATIC action (retry a failed job), confirmed both appear in the Action Center's Concluídas list and in the Timeline, confirmed the Automation Score updates without a page reload, zero console errors.

## Bug found during browser validation

**The Automation Score and "Concluídas" list showed stale data (0) immediately after a successful action, even though the action itself had genuinely succeeded.** Root cause: `POST /admin/actions/log` is deliberately fire-and-forget (audit logging must never block or fail the user-visible action — see the module comment in `hooks/use-action-execution.ts`), but the original code invalidated the `["admin", "logs"]` query in the *same* `onSuccess` callback that fired the fire-and-forget write, with no ordering between them. React Query would refetch the logs list before the write had actually landed server-side, so the Action Center's own execution history lagged behind reality by one interaction. Caught directly in the browser (not by a unit test — this is a timing issue across two real network calls, exactly the kind of thing static tests can't surface): a screenshot taken 1s after confirming "Aprovar meta" showed the toast "Ação concluída" *and* "Concluídas (0)" / "Nenhuma ação concluída ainda" side by side.

**Fix**: `logAction()` now returns its settled promise instead of discarding it; the `["admin", "logs"]` invalidation moved into a `.then()` chained onto that promise, so the query only refetches after the audit row genuinely exists. Every other invalidation (goals/tasks/jobs/calendar/observation) still fires immediately, since those reflect the underlying entity write — which `performExecute` already `await`s before `onSuccess` runs — and don't have this race. Re-verified in the browser: three consecutive real actions (one confirmed approval, two one-click retries) all appeared in "Concluídas" and in the Automation Score within the same render cycle as their toast, with no manual refresh needed.

## Known limitations

- **No "Running" state in practice.** Every workflow here is a synchronous HTTP call that resolves in well under a second — there's no background job queue involved in execution itself (retrying a job re-queues it for later processing, it doesn't run it inline). The Action Center's "Em execução" column is real (backed by actual React Query mutation state, not simulated), it's just almost always empty. Documented rather than removed, since a genuinely long-running action (e.g. a future multi-step agent workflow) would use the same column without any UI change.
- **No message-sending workflow.** The brief's own "follow up with a client" example (review context → generate a suggested message → send it) doesn't map onto any recommendation this system currently produces, and no admin-facing WhatsApp *send* endpoint exists yet (`OpenWAProvider.send_text` is only ever called from the Cognitive Pipeline's auto-reply path — see `WHATSAPP_VALIDATION.md`). Building one specifically to exercise this example would mean inventing both a new insight category and a new external-system-facing endpoint neither justified by an existing product need — left as a documented future opportunity rather than implemented speculatively.
- **"Delegate" isn't offered** as an alternative to completing/rescheduling an overdue task — this is a single-owner system with no second user to delegate to.
- **Automation Score history is bounded** to the last `ACTION_LOG_LIMIT` (200) action-log rows fetched by the Action Center page — enough for any realistic single day of use, but not a database-wide historical count. Same honest-about-sampling discipline as Phase 2's tick rollup, just not expected to matter in practice since the score itself is scoped to "today."

## Future opportunities

- A real "reply to a WhatsApp conversation" workflow once an admin-facing send endpoint exists — would slot into the same `ActionWorkflowControl`/classification/audit-log pattern without any structural change.
- Extending `create_followup_task`'s draft with a priority derived from the goal's own priority, instead of always defaulting to the Task system's default.
- Surfacing the Automation Score on the Daily Briefing's Executive Summary once there's a full day of real usage data to make it meaningful there.
