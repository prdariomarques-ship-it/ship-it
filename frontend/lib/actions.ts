// Action Center — Phase 4. Turns Operator/Briefing recommendations into
// one-click executable actions. Deliberately not a new execution engine:
// every action here calls an endpoint that already existed before this
// phase (PATCH /tasks/{id}, POST /goals/{id}/approve, POST
// /admin/jobs/{id}/retry, POST /tasks, POST /calendar). This module only
// adds two things those endpoints don't have on their own: a fixed,
// explainable SAFE/CONFIRM/MANUAL classification, and — via
// GET /admin/actions/log entries — a way to turn real executions into a
// measurable score. See ACTION_CENTER.md.

import type { AdminLogEntry } from "@/lib/admin-types";
import type { OperatorAction, OperatorActionKind, OperatorInsight } from "@/lib/operator";

export type ActionClassification = "SAFE_AUTOMATIC" | "REQUIRES_CONFIRMATION" | "MANUAL_ONLY";

export interface ActionClassificationInfo {
  classification: ActionClassification;
  reason: string;
}

/** One fixed classification per action kind — never a per-instance guess.
 * "Never automatically execute actions that affect external systems or
 * have significant consequences": every SAFE_AUTOMATIC kind here is
 * internal-only and reversible; everything that creates a new record with
 * system-guessed content, or hands real control to automation, requires an
 * explicit confirm click first. */
const CLASSIFICATION: Record<OperatorActionKind, ActionClassificationInfo> = {
  retry_job: {
    classification: "SAFE_AUTOMATIC",
    reason: "Reenviar um job falhado para a fila é seguro, reversível (pode ser cancelado de novo) e não afeta nenhum sistema externo.",
  },
  complete_task: {
    classification: "SAFE_AUTOMATIC",
    reason: "Marcar como concluída é reversível — a tarefa pode ser reaberta — e é uma alteração interna, não afeta sistemas externos.",
  },
  reschedule_task: {
    classification: "SAFE_AUTOMATIC",
    reason: "Adiar o prazo em 1 dia é reversível e é uma alteração interna, não afeta sistemas externos.",
  },
  approve_goal: {
    classification: "REQUIRES_CONFIRMATION",
    reason: "Aprovar libera a meta para execução automatizada subsequente; o próprio sistema de metas já exige confirmação explícita para isso.",
  },
  create_followup_task: {
    classification: "REQUIRES_CONFIRMATION",
    reason: "Cria uma nova tarefa com título e prazo sugeridos pelo sistema — revise antes de adicionar à sua lista.",
  },
  schedule_time: {
    classification: "REQUIRES_CONFIRMATION",
    reason: "Cria um evento novo na sua agenda com horário sugerido pelo sistema — confirme antes de reservar o horário.",
  },
};

/** Every recommendation resolves through a short *workflow*, not a bare
 * button — this is what the one-click (or one-click-plus-confirm) actually
 * does end-to-end. Shown in the UI so the user sees the real steps being
 * taken on their behalf; execution itself still takes the fewest possible
 * interactions (1 click when SAFE_AUTOMATIC, 2 when REQUIRES_CONFIRMATION —
 * see ActionClassification above). */
export const WORKFLOW_STEPS: Record<OperatorActionKind, string[]> = {
  complete_task: ["Abrir tarefa", "Marcar como concluída", "Registrar execução"],
  reschedule_task: ["Abrir tarefa", "Adiar prazo em 1 dia", "Registrar execução"],
  retry_job: ["Abrir job", "Reenviar para a fila", "Registrar execução"],
  approve_goal: ["Revisar meta", "Aprovar", "Liberar para a fila de execução", "Registrar execução"],
  create_followup_task: ["Revisar meta em risco", "Criar tarefa de acompanhamento", "Registrar execução"],
  schedule_time: ["Sugerir horário disponível", "Criar evento na agenda", "Registrar execução"],
};

export interface ActionPlan {
  insightId: string;
  category: OperatorInsight["category"];
  title: string;
  classification: ActionClassification;
  classificationReason: string;
  actionLabel: string;
  actionKind: OperatorActionKind | "open_related_item";
  targetId?: number;
  url?: string;
  estimatedMinutes: number | null;
  /** The workflow this action performs end-to-end, e.g. ["Abrir tarefa",
   * "Marcar como concluída", "Registrar execução"] — empty for
   * open_related_item, which isn't a workflow, just a link. */
  steps: string[];
  /** Only for create_followup_task/schedule_time — the exact content that
   * will be created, so a REQUIRES_CONFIRMATION step can show it before
   * the user confirms instead of executing blind. */
  draft?: FollowupTaskDraft | ScheduleTimeDraft;
}

function planFromAction(insight: OperatorInsight, action: OperatorAction): ActionPlan {
  const info = CLASSIFICATION[action.kind];
  return {
    insightId: insight.id,
    category: insight.category,
    title: insight.title,
    classification: info.classification,
    classificationReason: info.reason,
    actionLabel: action.label,
    actionKind: action.kind,
    targetId: action.targetId,
    estimatedMinutes: insight.estimatedMinutes,
    steps: WORKFLOW_STEPS[action.kind],
    draft: action.draft,
  };
}

/** The single answer to "what can I do about this, and how carefully?" —
 * `null` only for purely informational insights (already-automated,
 * "nothing urgent", historical change) that have nothing to act on at all.
 * Alternative (OR) branches of the same workflow — see planAlternatives. */
export function planAction(insight: OperatorInsight): ActionPlan | null {
  if (insight.action) return planFromAction(insight, insight.action);
  if (insight.manualOnlyAction) {
    return {
      insightId: insight.id,
      category: insight.category,
      title: insight.title,
      classification: "MANUAL_ONLY",
      classificationReason: insight.manualOnlyAction.reason,
      actionLabel: insight.manualOnlyAction.label,
      actionKind: "open_related_item",
      url: insight.manualOnlyAction.url,
      estimatedMinutes: insight.estimatedMinutes,
      steps: [],
    };
  }
  return null;
}

/** OR-branches of the primary workflow (e.g. "reschedule" instead of
 * "complete") — same classification rules, just a different terminal step. */
export function planAlternatives(insight: OperatorInsight): ActionPlan[] {
  return (insight.alternativeActions ?? []).map((action) => planFromAction(insight, action));
}

// --- Action Preview: "before executing any action, show a preview" — every
// field here answers one fixed question (what happens / what's affected /
// can it be undone / how long / side effects / how confident), computed
// once per action kind from real, already-established facts about that
// endpoint — never invented per instance. Shown in full for
// REQUIRES_CONFIRMATION (the second click IS the preview review); for
// SAFE_AUTOMATIC the same facts are available on hover, deliberately not a
// forced extra click, which would contradict "fewest possible interactions"
// for actions already judged safe and reversible. --------------------------

export interface ActionPreview {
  whatWillHappen: string;
  affectedEntities: string[];
  reversible: boolean;
  rollbackNote: string;
  estimatedExecutionTime: string;
  sideEffects: string[];
  executionConfidence: string;
}

const INSTANT_EXECUTION = "Instantâneo — chamada síncrona a um endpoint já existente e testado.";
const HIGH_EXECUTION_CONFIDENCE = "Alta — endpoint já existente, coberto por testes automatizados, sem dependência de sistema externo instável.";

const PREVIEW_TEMPLATE: Record<OperatorActionKind, Omit<ActionPreview, "affectedEntities">> = {
  complete_task: {
    whatWillHappen: "A tarefa será marcada como concluída.",
    reversible: true,
    rollbackNote: "Pode ser reaberta a qualquer momento, mudando o status de volta para pendente.",
    estimatedExecutionTime: INSTANT_EXECUTION,
    sideEffects: ["A tarefa some da lista de pendências e do Operador IA."],
    executionConfidence: HIGH_EXECUTION_CONFIDENCE,
  },
  reschedule_task: {
    whatWillHappen: "O prazo da tarefa será adiado em 1 dia.",
    reversible: true,
    rollbackNote: "O prazo pode ser ajustado novamente a qualquer momento.",
    estimatedExecutionTime: INSTANT_EXECUTION,
    sideEffects: ["A tarefa deixa de aparecer como atrasada até o novo prazo."],
    executionConfidence: HIGH_EXECUTION_CONFIDENCE,
  },
  retry_job: {
    whatWillHappen: "O job falhado será reenviado para a fila de processamento.",
    reversible: true,
    rollbackNote: "Pode ser cancelado novamente enquanto estiver na fila (ação 'Cancelar' em Jobs).",
    estimatedExecutionTime: "Instantâneo para a chamada em si — o reprocessamento do job roda depois, em segundo plano, de forma assíncrona.",
    sideEffects: ["As tentativas (attempts) são zeradas.", "O job passa de 'falhado' para 'na fila'."],
    executionConfidence: HIGH_EXECUTION_CONFIDENCE,
  },
  approve_goal: {
    whatWillHappen: "A meta será aprovada e liberada para a fila de execução automatizada.",
    reversible: false,
    rollbackNote: "Não pode ser desfeito automaticamente — não existe uma ação de 'reprovar' depois de aprovada.",
    estimatedExecutionTime: INSTANT_EXECUTION,
    sideEffects: ["A meta passa a poder ser processada pelo Cognitive Pipeline sem nova confirmação sua."],
    executionConfidence: HIGH_EXECUTION_CONFIDENCE,
  },
  create_followup_task: {
    whatWillHappen: "Uma nova tarefa será criada com o título e prazo mostrados abaixo.",
    reversible: true,
    rollbackNote: "A tarefa criada pode ser excluída manualmente depois, como qualquer outra tarefa.",
    estimatedExecutionTime: INSTANT_EXECUTION,
    sideEffects: ["Nenhum sistema externo é afetado — a tarefa é criada apenas no Dario OS."],
    executionConfidence: HIGH_EXECUTION_CONFIDENCE,
  },
  schedule_time: {
    whatWillHappen: "Um novo evento será criado na sua agenda com o horário mostrado abaixo.",
    reversible: true,
    rollbackNote: "O evento criado pode ser excluído manualmente depois, como qualquer outro evento.",
    estimatedExecutionTime: INSTANT_EXECUTION,
    sideEffects: [
      "Nenhuma verificação automática de conflito de horário é feita — revise sua agenda antes de confirmar.",
      "Nenhum participante é notificado — o evento é local ao Dario OS.",
    ],
    executionConfidence: HIGH_EXECUTION_CONFIDENCE,
  },
};

/** `null` for open_related_item — that's navigation, not an action with
 * consequences to preview. */
export function buildActionPreview(plan: ActionPlan): ActionPreview | null {
  if (plan.actionKind === "open_related_item") return null;
  const template = PREVIEW_TEMPLATE[plan.actionKind];
  const affectedEntities = plan.draft ? [plan.draft.title] : [plan.title];
  return { ...template, affectedEntities };
}

// --- Drafts for the two actions that create a new record: shown to the user
// before execution (never a silent guess), built from a fixed, documented
// rule — same discipline as the 30min-default calendar-conflict assumption
// in lib/operator.ts. -----------------------------------------------------

export interface FollowupTaskDraft {
  title: string;
  due_date: string;
}

/** Due today, end of day — the insight that triggers this ("meta em risco")
 * already means the deadline is close, so the follow-up nudges same-day
 * action rather than pushing it further out. */
export function buildFollowupTaskDraft(goalTitle: string, now: Date): FollowupTaskDraft {
  const due = new Date(now);
  due.setUTCHours(23, 59, 0, 0);
  return { title: `Avançar meta: ${goalTitle}`, due_date: due.toISOString() };
}

export interface ScheduleTimeDraft {
  title: string;
  starts_at: string;
  ends_at: string;
}

/** Starts one hour from now, 30 minutes long — same conservative default
 * duration already used for calendar-conflict detection when an event has
 * no end time (see eventEnd() in lib/operator.ts). */
export function buildScheduleTimeDraft(goalTitle: string, now: Date): ScheduleTimeDraft {
  const start = new Date(now.getTime() + 60 * 60_000);
  const end = new Date(start.getTime() + 30 * 60_000);
  return { title: `Trabalhar em: ${goalTitle}`, starts_at: start.toISOString(), ends_at: end.toISOString() };
}

// --- Automation Score: derived only from real /admin/actions/log entries
// (successful executions actually recorded) plus a real-time count of
// currently-pending confirmations — never a fabricated estimate. ----------

export interface AutomationScore {
  actionsCompletedToday: number;
  estimatedMinutesSavedToday: number;
  /** Equal to actionsCompletedToday by construction: every logged action is,
   * by design, a one-click replacement for a manual multi-step operation
   * (open a screen, find the record, edit it, save) — see ACTION_CENTER.md
   * "Why this number equals actions completed". Kept as a separate field
   * because it answers a different question ("how many manual chores did
   * this replace"), even though today the two numbers always match. */
  manualStepsAvoidedToday: number;
  pendingConfirmations: number;
}

const ACTION_LOG_SOURCE_PREFIX = "admin:action.";

function startOfDay(date: Date): Date {
  const d = new Date(date);
  d.setUTCHours(0, 0, 0, 0);
  return d;
}

export function computeAutomationScore(
  logs: AdminLogEntry[],
  pendingConfirmations: number,
  now: Date
): AutomationScore {
  const today = startOfDay(now);
  const successesToday = logs.filter((log) => {
    if (!log.source.startsWith(ACTION_LOG_SOURCE_PREFIX)) return false;
    if (log.payload?.result !== "success") return false;
    return new Date(log.created_at).getTime() >= today.getTime();
  });
  const estimatedMinutesSavedToday = successesToday.reduce((sum, log) => {
    const minutes = log.payload?.estimated_minutes;
    return sum + (typeof minutes === "number" ? minutes : 0);
  }, 0);

  return {
    actionsCompletedToday: successesToday.length,
    estimatedMinutesSavedToday,
    manualStepsAvoidedToday: successesToday.length,
    pendingConfirmations,
  };
}

// --- Action Center groupings: Pending / Waiting for confirmation / Completed
// / Failed — built from the current insight list (pending/waiting) plus
// today's action-log entries (completed/failed). --------------------------

export interface ActionLogItem {
  id: number;
  createdAt: string;
  actionType: string;
  category: string;
  recommendationTitle: string;
  result: "success" | "failure";
  relatedEntities: string[];
  estimatedMinutes: number | null;
  detail: string | null;
}

export function parseActionLog(log: AdminLogEntry): ActionLogItem | null {
  if (!log.source.startsWith(ACTION_LOG_SOURCE_PREFIX)) return null;
  const p = log.payload as {
    action_type?: string;
    category?: string;
    recommendation_title?: string;
    result?: string;
    related_entities?: string[];
    estimated_minutes?: number | null;
    detail?: string | null;
  };
  return {
    id: log.id,
    createdAt: log.created_at,
    actionType: p.action_type ?? log.source.slice(ACTION_LOG_SOURCE_PREFIX.length),
    category: p.category ?? "",
    recommendationTitle: p.recommendation_title ?? log.message,
    result: p.result === "failure" ? "failure" : "success",
    relatedEntities: p.related_entities ?? [],
    estimatedMinutes: typeof p.estimated_minutes === "number" ? p.estimated_minutes : null,
    detail: p.detail ?? null,
  };
}
