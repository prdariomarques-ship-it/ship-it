// AI Operator Center — deterministic, explainable synthesis over data the
// dashboard already fetches (goals, tasks, calendar, jobs, CurrentContext).
// Deliberately not an LLM call: every insight here is a plain rule over real
// records, so "why" is always the literal condition that fired — no black
// box, nothing to hallucinate. See AI_OPERATOR.md.

import type {
  CalendarEventRead,
  CurrentContext,
  GoalRead,
  JobRead,
  TaskRead,
} from "@/lib/admin-types";
import { buildFollowupTaskDraft, buildScheduleTimeDraft } from "@/lib/actions";
import type { FollowupTaskDraft, ScheduleTimeDraft } from "@/lib/actions";

export type OperatorCategory =
  | "highest_priority"
  | "follow_up"
  | "missed_task"
  | "calendar_conflict"
  | "risk"
  | "opportunity"
  | "automatable"
  | "recent_change";

/** The four buckets the Operator groups every actionable insight into (not
 * `recent_change`, which is informational history, not a to-do — that's
 * `Timeline`'s job, see MEMORY_TIMELINE.md). */
export type OperatorBucket = "urgent" | "today" | "opportunity" | "automation";

export type Confidence = "high" | "medium" | "low";
export type Severity = "urgent" | "attention" | "info";

/** Fixed, tier-based scores — not a continuous ML confidence. Deliberately
 * round numbers (95/65/35) so nobody mistakes this for false precision:
 * every insight here is a rule firing on real data, and the tier reflects
 * whether that rule is a direct fact (high) or a judgment call (medium/low)
 * — see AI_OPERATOR.md "Why these three numbers, not a spectrum". */
const CONFIDENCE_SCORE: Record<Confidence, number> = { high: 95, medium: 65, low: 35 };

// Every kind here targets one concrete, already-identified entity — the
// generic "no specific entity, just go look at something" case is handled
// separately by lib/actions.ts's MANUAL_ONLY fallback, not by this union.
export type OperatorActionKind =
  | "approve_goal"
  | "retry_job"
  | "complete_task"
  | "reschedule_task"
  | "create_followup_task"
  | "schedule_time";

export interface OperatorAction {
  label: string;
  kind: OperatorActionKind;
  targetId: number;
  /** Only for kinds that create a new record (create_followup_task,
   * schedule_time) — the exact content that will be created, computed here
   * where the real entity (goal) is available, so the UI can show it before
   * the user confirms instead of re-deriving it from insight.title. */
  draft?: FollowupTaskDraft | ScheduleTimeDraft;
}

export interface OperatorInsight {
  id: string;
  bucket: OperatorBucket;
  category: OperatorCategory;
  title: string;
  reason: string;
  impact: string;
  /** 0-100, see CONFIDENCE_SCORE. */
  confidence: number;
  confidenceTier: Confidence;
  /** Minutes for the concrete action itself (approve/retry/reschedule) when
   * that's a fixed, small, defensible estimate. `null` — not a fabricated
   * number — for open-ended work (finishing a goal, doing an overdue task)
   * where the real effort depends on the task itself, not on this system. */
  estimatedMinutes: number | null;
  severity: Severity;
  action?: OperatorAction;
  /** OR-branches of the same workflow (e.g. "Resolve overdue task": mark
   * completed OR reschedule) — alternatives to `action`, not additional
   * required steps. See lib/actions.ts's WORKFLOW_STEPS for what each kind
   * actually does end-to-end. */
  alternativeActions?: OperatorAction[];
  /** Set only when the insight has no safe/confirmable action to offer —
   * the honest MANUAL_ONLY case (see lib/actions.ts): a link to where a
   * human has to go look, plus why the system won't decide for them. */
  manualOnlyAction?: { label: string; url: string; reason: string };
}

export interface OperatorInput {
  readyGoals: GoalRead[];
  awaitingApprovalGoals: GoalRead[];
  tasks: TaskRead[];
  calendarEvents: CalendarEventRead[];
  failedJobs: JobRead[];
  pendingJobs: JobRead[];
  context: CurrentContext | undefined;
  previousContext: CurrentContext | undefined;
  whatsappConnected: boolean | undefined;
  now?: Date;
}

const PRIORITY_LABEL: Record<string, string> = {
  low: "baixa",
  medium: "média",
  high: "alta",
  urgent: "urgente",
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR");
}

function isOverdue(dueDate: string | null, now: Date): boolean {
  return !!dueDate && new Date(dueDate).getTime() < now.getTime();
}

function isDueSoon(dueDate: string | null, now: Date, hours: number): boolean {
  if (!dueDate) return false;
  const dueTime = new Date(dueDate).getTime();
  const horizon = now.getTime() + hours * 3_600_000;
  return dueTime >= now.getTime() && dueTime <= horizon;
}

/** Missing end time doesn't mean zero duration — assume a conservative 30min
 * default, same as most calendar UIs, and say so explicitly in the reason
 * text whenever that assumption drives a conflict finding (never a silent
 * guess). */
function eventEnd(event: CalendarEventRead): { end: Date; assumed: boolean } {
  if (event.ends_at) return { end: new Date(event.ends_at), assumed: false };
  return { end: new Date(new Date(event.starts_at).getTime() + 30 * 60_000), assumed: true };
}

function findCalendarConflicts(events: CalendarEventRead[]): OperatorInsight[] {
  const insights: OperatorInsight[] = [];
  const seen = new Set<string>();

  for (let i = 0; i < events.length; i++) {
    for (let j = i + 1; j < events.length; j++) {
      const a = events[i];
      const b = events[j];
      const aStart = new Date(a.starts_at).getTime();
      const bStart = new Date(b.starts_at).getTime();
      const { end: aEnd, assumed: aAssumed } = eventEnd(a);
      const { end: bEnd, assumed: bAssumed } = eventEnd(b);

      const overlaps = aStart < bEnd.getTime() && bStart < aEnd.getTime();
      if (!overlaps) continue;

      const pairKey = [a.id, b.id].sort().join("-");
      if (seen.has(pairKey)) continue;
      seen.add(pairKey);

      const assumed = aAssumed || bAssumed;
      const assumedNote = assumed
        ? " (duração de 30min assumida para o evento sem horário de término)"
        : "";
      const tier: Confidence = assumed ? "medium" : "high";
      insights.push({
        id: `conflict-${pairKey}`,
        bucket: "today",
        category: "calendar_conflict",
        title: `Conflito de agenda: "${a.title}" e "${b.title}"`,
        reason: `"${a.title}" (${formatDate(a.starts_at)}) sobrepõe "${b.title}" (${formatDate(b.starts_at)})${assumedNote}.`,
        impact: "Evita perder ou chegar atrasado a um dos dois compromissos.",
        confidence: CONFIDENCE_SCORE[tier],
        confidenceTier: tier,
        estimatedMinutes: 5,
        severity: "attention",
      });
    }
  }
  return insights;
}

function findRecentChanges(
  context: CurrentContext | undefined,
  previous: CurrentContext | undefined
): OperatorInsight[] {
  if (!context || !previous) return [];
  const dimensions: { key: keyof CurrentContext; label: string }[] = [
    { key: "goals", label: "Metas" },
    { key: "tasks", label: "Tarefas" },
    { key: "calendar", label: "Agenda" },
    { key: "pending_work", label: "Trabalho pendente" },
    { key: "conversations", label: "Conversas" },
  ];

  const insights: OperatorInsight[] = [];
  for (const { key, label } of dimensions) {
    const currentList = context[key];
    const previousList = previous[key];
    if (!Array.isArray(currentList) || !Array.isArray(previousList)) continue;
    const delta = currentList.length - previousList.length;
    if (delta === 0) continue;
    insights.push({
      id: `change-${key}`,
      bucket: "today",
      category: "recent_change",
      title: `${label}: ${previousList.length} → ${currentList.length}`,
      reason: `Mudou desde a última atualização (${delta > 0 ? "+" : ""}${delta}).`,
      impact: "Informativo — não requer ação.",
      confidence: CONFIDENCE_SCORE.high,
      confidenceTier: "high",
      estimatedMinutes: null,
      severity: "info",
    });
  }
  return insights;
}

export function buildOperatorInsights(input: OperatorInput): OperatorInsight[] {
  const now = input.now ?? new Date();
  const insights: OperatorInsight[] = [];

  // --- Follow-ups: goals awaiting approval -----------------------------------
  for (const goal of input.awaitingApprovalGoals) {
    insights.push({
      id: `approve-${goal.id}`,
      bucket: "today",
      category: "follow_up",
      title: `Aprovar meta: ${goal.title}`,
      reason: "Criada com requires_approval — precisa da sua decisão antes de começar.",
      impact: "Libera a meta para entrar na fila de execução.",
      confidence: CONFIDENCE_SCORE.high,
      confidenceTier: "high",
      estimatedMinutes: 1,
      severity: "attention",
      action: { label: "Aprovar", kind: "approve_goal", targetId: goal.id },
    });
  }

  // --- Urgent: failed jobs -------------------------------------------------------
  for (const job of input.failedJobs) {
    insights.push({
      id: `retry-${job.id}`,
      bucket: "urgent",
      category: "risk",
      title: `Job falhou: ${job.name}`,
      reason: job.last_error
        ? `Esgotou as tentativas (${job.attempts}/${job.max_attempts}): ${job.last_error}`
        : `Esgotou as tentativas (${job.attempts}/${job.max_attempts}).`,
      impact: "Sem retry, esse trabalho em segundo plano fica parado indefinidamente.",
      confidence: CONFIDENCE_SCORE.high,
      confidenceTier: "high",
      estimatedMinutes: 1,
      severity: "urgent",
      action: { label: "Tentar novamente", kind: "retry_job", targetId: job.id },
    });
  }

  // --- Urgent: missed tasks (overdue) / today: due soon ---------------------------
  for (const task of input.tasks) {
    if (task.status !== "pending") continue;
    if (isOverdue(task.due_date, now)) {
      insights.push({
        id: `missed-${task.id}`,
        bucket: "urgent",
        category: "missed_task",
        title: `Tarefa atrasada: ${task.title}`,
        reason: `Venceu em ${formatDate(task.due_date as string)} (prioridade ${PRIORITY_LABEL[task.priority] ?? task.priority}).`,
        impact: "Quanto mais atrasa, maior o risco de esquecer de vez.",
        confidence: CONFIDENCE_SCORE.high,
        confidenceTier: "high",
        estimatedMinutes: null,
        severity: "attention",
        action: { label: "Concluir tarefa", kind: "complete_task", targetId: task.id },
        alternativeActions: [{ label: "Adiar 1 dia", kind: "reschedule_task", targetId: task.id }],
      });
    } else if (isDueSoon(task.due_date, now, 48)) {
      insights.push({
        id: `followup-task-${task.id}`,
        bucket: "today",
        category: "follow_up",
        title: `Vence em breve: ${task.title}`,
        reason: `Prazo ${formatDate(task.due_date as string)} — ainda não vencida, mas dentro de 48h.`,
        impact: "Fazer agora evita que vire uma tarefa atrasada amanhã.",
        confidence: CONFIDENCE_SCORE.high,
        confidenceTier: "high",
        estimatedMinutes: null,
        severity: "info",
        action: { label: "Concluir tarefa", kind: "complete_task", targetId: task.id },
        alternativeActions: [{ label: "Adiar 1 dia", kind: "reschedule_task", targetId: task.id }],
      });
    }
  }

  // --- Today: top ready goals -------------------------------------------------
  const topGoals = input.readyGoals.slice(0, 3);
  for (const goal of topGoals) {
    insights.push({
      id: `priority-goal-${goal.id}`,
      bucket: goal.priority === "urgent" ? "urgent" : "today",
      category: "highest_priority",
      title: goal.title,
      reason: `Prioridade ${PRIORITY_LABEL[goal.priority] ?? goal.priority}, ${goal.progress_percent}% concluída${
        goal.deadline ? `, prazo ${formatDate(goal.deadline)}` : ""
      } — próxima na fila por pontuação de urgência.`,
      impact: "Mantém a meta de maior pontuação avançando em vez de parada na fila.",
      confidence: CONFIDENCE_SCORE.high,
      confidenceTier: "high",
      estimatedMinutes: null,
      severity: goal.priority === "urgent" ? "urgent" : "attention",
      action: {
        label: "Agendar tempo para isso",
        kind: "schedule_time",
        targetId: goal.id,
        draft: buildScheduleTimeDraft(goal.title, now),
      },
    });
  }

  // --- Urgent: goal deadline very close + low progress ----------------------------
  for (const goal of input.readyGoals) {
    if (!goal.deadline) continue;
    const daysLeft = (new Date(goal.deadline).getTime() - now.getTime()) / 86_400_000;
    if (daysLeft >= 0 && daysLeft <= 3 && goal.progress_percent < 50) {
      insights.push({
        id: `risk-goal-${goal.id}`,
        bucket: daysLeft <= 1 ? "urgent" : "today",
        category: "risk",
        title: `Meta em risco: ${goal.title}`,
        reason: `Prazo em ${Math.ceil(daysLeft)} dia(s), mas só ${goal.progress_percent}% concluída.`,
        impact: "Sem atenção agora, o prazo provavelmente não será cumprido.",
        confidence: CONFIDENCE_SCORE.medium,
        confidenceTier: "medium",
        estimatedMinutes: null,
        severity: "attention",
        action: {
          label: "Criar tarefa de acompanhamento",
          kind: "create_followup_task",
          targetId: goal.id,
          draft: buildFollowupTaskDraft(goal.title, now),
        },
      });
    }
  }

  // --- Today: calendar conflicts ------------------------------------------------
  insights.push(
    ...findCalendarConflicts(input.calendarEvents).map((insight) => ({
      ...insight,
      manualOnlyAction: {
        label: "Abrir agenda",
        url: "/admin",
        reason: "Decidir qual compromisso manter (ou remarcar) exige julgamento humano — o sistema não escolhe por você.",
      },
    }))
  );

  // --- Urgent: WhatsApp disconnected -----------------------------------------------
  if (input.whatsappConnected === false) {
    insights.push({
      id: "risk-whatsapp",
      bucket: "urgent",
      category: "risk",
      title: "WhatsApp desconectado",
      reason: "A sessão precisa ser reconectada (QR code no gateway) para o Dario OS continuar respondendo mensagens.",
      impact: "Enquanto desconectado, nenhuma mensagem é enviada ou recebida automaticamente.",
      confidence: CONFIDENCE_SCORE.high,
      confidenceTier: "high",
      estimatedMinutes: 10,
      severity: "urgent",
      manualOnlyAction: {
        label: "Abrir WhatsApp",
        url: "/admin/whatsapp",
        reason: "Requer escanear o QR code no dispositivo físico conectado — não pode ser feito pelo painel.",
      },
    });
  }

  // --- Today: degraded observation sources -----------------------------------------
  if (input.context && input.context.degraded_sources.length > 0) {
    insights.push({
      id: "risk-observation-degraded",
      bucket: "today",
      category: "risk",
      title: "Observação do sistema incompleta",
      reason: `Fontes indisponíveis na última leitura: ${input.context.degraded_sources.join(", ")}.`,
      impact: "O Contexto Atual pode estar incompleto até a próxima leitura bem-sucedida.",
      confidence: CONFIDENCE_SCORE.high,
      confidenceTier: "high",
      estimatedMinutes: null,
      severity: "attention",
      manualOnlyAction: {
        label: "Abrir painel",
        url: "/admin",
        reason: "Uma fonte de observação indisponível é um problema de infraestrutura, não algo que um clique corrige.",
      },
    });
  }

  // --- Opportunity: a goal close to done -----------------------------------------
  for (const goal of input.readyGoals) {
    if (goal.progress_percent >= 80) {
      insights.push({
        id: `opportunity-goal-${goal.id}`,
        bucket: "opportunity",
        category: "opportunity",
        title: `Quase lá: ${goal.title}`,
        reason: `${goal.progress_percent}% concluída — pode dar para terminar hoje.`,
        impact: "Uma meta a menos na fila, com pouco esforço adicional.",
        confidence: CONFIDENCE_SCORE.medium,
        confidenceTier: "medium",
        estimatedMinutes: null,
        severity: "info",
        manualOnlyAction: {
          label: "Abrir meta",
          url: "/admin",
          reason: "Terminar a meta exige o trabalho real, não uma ação de um clique.",
        },
      });
    }
  }

  // --- Opportunity: everything quiet -------------------------------------------
  const noUrgentWork =
    input.failedJobs.length === 0 &&
    input.awaitingApprovalGoals.length === 0 &&
    !input.tasks.some((t) => t.status === "pending" && isOverdue(t.due_date, now));
  if (noUrgentWork && input.readyGoals.length > 0) {
    insights.push({
      id: "opportunity-quiet",
      bucket: "opportunity",
      category: "opportunity",
      title: "Nenhum pendente urgente agora",
      reason: "Sem job falhado, meta aguardando aprovação ou tarefa atrasada — bom momento para avançar a próxima meta ou revisar o backlog.",
      impact: "Momento ideal para trabalho profundo, sem interrupções pendentes.",
      confidence: CONFIDENCE_SCORE.medium,
      confidenceTier: "medium",
      estimatedMinutes: null,
      severity: "info",
    });
  }

  // --- Automation: already-recurring goals + background jobs -----------------------
  for (const goal of input.readyGoals) {
    if (goal.recurrence_interval_days) {
      insights.push({
        id: `automatable-goal-${goal.id}`,
        bucket: "automation",
        category: "automatable",
        title: `Já automatizada: ${goal.title}`,
        reason: `Recorrente a cada ${goal.recurrence_interval_days} dia(s) — uma nova ocorrência é criada sozinha ao concluir esta.`,
        impact: "Nenhuma ação necessária — o sistema já recria essa meta sozinho.",
        confidence: CONFIDENCE_SCORE.high,
        confidenceTier: "high",
        estimatedMinutes: null,
        severity: "info",
      });
    }
  }
  if (input.pendingJobs.length > 0) {
    insights.push({
      id: "automatable-jobs",
      bucket: "automation",
      category: "automatable",
      title: `${input.pendingJobs.length} job(s) em andamento automaticamente`,
      reason: "Trabalho em segundo plano já rodando sem intervenção manual (fila de jobs).",
      impact: "Nenhuma ação necessária — já está automatizado.",
      confidence: CONFIDENCE_SCORE.high,
      confidenceTier: "high",
      estimatedMinutes: null,
      severity: "info",
    });
  }

  // --- Recently observed changes (history, not a to-do — see Timeline) ------------
  insights.push(...findRecentChanges(input.context, input.previousContext));

  return insights;
}

export function confidenceSummary(insights: OperatorInsight[]): string {
  if (insights.length === 0) return "Nenhuma recomendação no momento.";
  const high = insights.filter((i) => i.confidenceTier === "high").length;
  return `${high} de ${insights.length} recomendações são de alta confiança (baseadas em dados diretos, não inferência).`;
}

/** The single most important thing to do right now — the direct answer to
 * "what should I do right now?" (urgent first, then today's top item). Never
 * `recent_change` (informational, not a to-do). Returns null only when
 * there is truly nothing actionable, in which case the UI says so plainly
 * rather than showing an empty state that looks broken. */
export function topInsight(insights: OperatorInsight[]): OperatorInsight | null {
  const actionable = insights.filter((i) => i.category !== "recent_change");
  const urgent = actionable.filter((i) => i.bucket === "urgent");
  if (urgent.length > 0) return urgent[0];
  const today = actionable.filter((i) => i.bucket === "today");
  if (today.length > 0) return today[0];
  return null;
}
