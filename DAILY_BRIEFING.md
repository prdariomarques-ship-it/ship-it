# Daily Briefing — Phase 3

An executive briefing, not a dashboard. Lives at `/admin/briefing`. The goal, verbatim from the brief: *"The system spent the night thinking for me."* Everything on the page is composed from Phase 1's insights (`lib/operator.ts`) and Phase 2's timeline (`lib/timeline.ts`) — Phase 3 adds zero new data sources, only a narrative and decision-support layer on top of what those two phases already compute.

## What's on the page

1. **Opening narrative** — one paragraph, plain language, built entirely from real counts (`greetingParts` in `lib/briefing.ts`): how many priorities, whether anything is overdue, whether there's a calendar conflict, whether WhatsApp is connected, whether there are new opportunities, and an estimated total time to clear today's priorities. No two days read the same because no two days *are* the same — there's no template text disconnected from the underlying numbers.
2. **Executive Summary** — five facts, each pulled straight from the computed insight/timeline sets: what changed overnight, what deserves attention, the biggest opportunity (or `null`), the biggest risk (or `null`), estimated workload in minutes, and a recommended order.
3. **Prioridades / Riscos / Oportunidades** — three columns of `BriefingRecommendationCard`s, each wrapping a Phase 1 `OperatorInsight` with two new fields: `whyNow` and `consequenceIfIgnored` (see below). Every card keeps Phase 1's existing why/confidence/impact/estimated-time/one-click-action/dismiss/snooze — Phase 3 doesn't replace that, it adds decision support on top.
4. **Execution Plan** — Morning / Afternoon / Evening columns. Real calendar events go in the slot they're actually scheduled for; non-calendar urgent work is front-loaded to the morning, today-bucket work to the afternoon. Captioned explicitly in the UI: *"sugestão por urgência, não uma agenda imposta"* — it is a suggestion, never presented as an imposed schedule.
5. **Agenda de hoje / Tarefas de hoje** — reuses the existing `CalendarPanel`/`TasksPanel` components, filtered to today.
6. **Progresso de metas / Conversas recentes** — reuses `GoalsPanel` and Phase 2's `TimelineEventCard`.
7. **Recomendações da IA / O que mudou desde ontem / Saúde do dia** — automations list, a `ChangeSummary` card (Phase 2's `summarizeChanges`), and the `HealthScoreCard`.
8. **Closing line** — "if you can only do one thing today, do this" — names the single top-ranked insight, or an honest fallback ("revisar as oportunidades abaixo — não há nada urgente pendente") when nothing is urgent.

## Decision support: `whyNow` / `consequenceIfIgnored`

The brief requires every recommendation to explain not just *what* and *why*, but *why now* and *what happens if I ignore it*. These are computed by a `switch` on `OperatorInsight.category` (`whyNow()`/`consequenceIfIgnored()` in `lib/briefing.ts`) — one fixed, documented answer per category, not a per-instance guess:

| Category | Why now | Consequence if ignored |
| --- | --- | --- |
| `missed_task` | Já está atrasada — cada dia a mais reduz a chance de ser feita. | Risco real de a tarefa ser esquecida e o prazo original perdido de vez. |
| `follow_up` | Uma decisão sua é o único passo faltando para destravar isso. | A meta continua fora da fila de execução. |
| `calendar_conflict` | Os dois compromissos coincidem — decidir agora evita escolher às pressas na hora. | Um dos dois compromissos será perdido ou remarcado às pressas. |
| `risk` (urgent) | Já passou do ponto ideal de ação. | O problema tende a se agravar sem intervenção. |
| `risk` (non-urgent) | Ainda dá para agir antes de virar urgência. | Vira urgência nos próximos dias. |
| `highest_priority` | É a meta com maior pontuação de urgência na fila agora. | A meta fica mais tempo parada na fila. |
| `opportunity` | A janela existe hoje; nada garante que continue amanhã. | A oportunidade pode não estar mais disponível depois. |
| `automatable` | Não precisa da sua atenção — já está resolvido. | Nenhuma — já está sendo cuidado automaticamente. |

Same discipline as Phase 1's confidence tiers and Phase 2's importance scores: two insights of the same category get the same *kind* of answer because the underlying situation really is the same kind of situation — never a fabricated per-instance rationale.

## Health Score — six factors, fixed weights, none double-counted

Starts at 100, `Math.max(0, 100 - sum(deductions))`. Every deduction is itemized in the UI with its own label and reason (`computeHealthScore()` in `lib/briefing.ts`):

| Factor | Points | Cap |
| --- | --- | --- |
| Tarefas atrasadas | -5 each | 25 |
| Progresso de metas (metas em risco: prazo ≤3 dias e progresso <50%) | -10 each | 20 |
| Conflitos de agenda | -15 each | 30 |
| Follow-ups não resolvidos (metas aguardando aprovação) | -8 each | 24 |
| Saúde do sistema — WhatsApp desconectado | -20 flat | — |
| Saúde do sistema — fontes de observação degradadas | -10 each | 20 |
| Ações pendentes — jobs falhados | -10 each | 30 |

The `formula` field renders the literal arithmetic (`"100 - 15 - 8 - 20 - 10 - 10 = 47"`) rather than just the final number, so the score is always auditable from the card itself — never a black-box number. Verified against the demo environment: a day with 3 overdue tasks (-15), 1 unresolved follow-up (-8), WhatsApp disconnected (-20), 1 degraded source (-10), and 1 failed job (-10) correctly scored **47/100**, matching the formula shown in the UI.

## Execution Plan bucketing

Calendar events are placed by their actual `starts_at` hour, converted with `getUTCHours()` — **not** `getHours()`. This matters because every other date boundary in the codebase (`startOfDay`, `filterRange` in `lib/timeline.ts`) is UTC-based; using local time here would have made the execution plan disagree with the rest of the page about what "morning" means. Non-calendar work has no natural time slot, so it's ordered by urgency instead: urgent-bucket insights to Morning (front-load the hard things), today-bucket insights to Afternoon. Evening is reserved for whatever calendar events actually land there — there's no synthetic "evening work" invented to fill the column.

## Architecture

```
frontend/lib/briefing.ts                    buildDailyBriefing() — composes
                                              buildOperatorInsights() (Phase 1) +
                                              buildTimelineEvents()/summarizeChanges()
                                              (Phase 2) into one document.
                                              Pure function, no React, no fetch.
frontend/components/admin/
  BriefingRecommendationCard.tsx             recommendation card (+ AutomationCard)
  HealthScoreCard.tsx                        score + itemized deductions
app/admin/briefing/page.tsx                  fetches the same sources Phase 1 + 2
                                              already fetch, composes via useMemo,
                                              renders the 8 sections above
```

No backend changes this phase — `buildDailyBriefing` consumes exactly the data Phase 1's Operator Center and Phase 2's Timeline already fetch (goals, tasks, calendar events, jobs, observation context, WhatsApp status, recent messages, logs). Nav entry added as **"Briefing Diário"**, positioned above Timeline.

## Testing

- `frontend/tests/briefing.test.ts` — 21 unit tests: health score (perfect day = 100, each deduction cap, WhatsApp-disconnected flat deduction, floor at 0, formula string correctness), `whyNow`/`consequenceIfIgnored` present for every recommendation, execution plan (the UTC-hour bucketing regression test, duration computed from `starts_at`/`ends_at`, urgent→morning/today→afternoon ordering), greeting content (correctly names overdue tasks/conflicts/WhatsApp status, honest quiet-day phrasing when nothing needs attention), closing line (names the top priority, or the honest fallback when nothing is urgent), `changedSinceLastLogin` (null on first visit, populated otherwise), executive summary (`biggestRisk`/`biggestOpportunity` correctly `null` when there are none — never fabricated).
- Full suite: **206/206 frontend** (185 prior + 21 new), **877/877 backend** (unchanged this phase). `tsc --noEmit`, `next lint`, `next build` all clean — `/admin/briefing` compiles at 9.83 kB (First Load JS 137 kB).
- Browser-verified (Playwright) against the same isolated demo environment used for Phases 1 and 2: logged in, navigated to `/admin/briefing`, confirmed all eight sections render with real seeded data (5 priorities, 2 risks, 0 new opportunities, a 47/100 health score with itemized deductions, an execution plan split across Morning/Afternoon/Evening, and a closing line naming the top-ranked recommendation), zero console errors.

## Bug found during this phase

**`periodForHour` used `.getHours()` (local/environment timezone) instead of `.getUTCHours()`.** Caught immediately by this phase's own execution-plan test (`expected 'afternoon' to be 'evening'`) before it ever reached a screenshot — a calendar event's bucket depended on the machine's local timezone rather than the event's actual UTC time, which would have silently disagreed with every other date boundary already established in `lib/timeline.ts`. Fixed to `.getUTCHours()`; regression-tested.

## Known limitations

- **`topPriorities` is capped at 5** (`priorityInsights.slice(0, 5)`) to keep the briefing scannable within the "five seconds" goal carried over from Phase 1 — a busier day's remaining urgent/today items are still visible in full on the Operator Center, just not repeated here.
- **`estimatedWorkloadMinutes` sums only `topPriorities` and `risks`**, not opportunities or automations — consistent with the brief's framing of "workload" as work that must get done today, not optional upside.
- **`atRiskGoals` (used only for the health score) is a fixed heuristic** — deadline within 3 days and progress under 50% — the same kind of documented, non-configurable threshold already used throughout Phase 1's insight rules, not a per-goal judgment call.
- Inherits every known limitation already documented in `AI_OPERATOR.md` and `MEMORY_TIMELINE.md`, since this phase is a composition layer over both.
