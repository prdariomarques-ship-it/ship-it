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

export type OperatorCategory =
  | "highest_priority"
  | "follow_up"
  | "missed_task"
  | "calendar_conflict"
  | "risk"
  | "opportunity"
  | "automatable"
  | "recent_change";

export type Confidence = "high" | "medium" | "low";
export type Severity = "urgent" | "attention" | "info";

export interface OperatorAction {
  label: string;
  kind: "approve_goal" | "retry_job";
  targetId: number;
}

export interface OperatorInsight {
  id: string;
  category: OperatorCategory;
  title: string;
  reason: string;
  confidence: Confidence;
  severity: Severity;
  action?: OperatorAction;
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

      const assumedNote =
        aAssumed || bAssumed
          ? " (duração de 30min assumida para o evento sem horário de término)"
          : "";
      insights.push({
        id: `conflict-${pairKey}`,
        category: "calendar_conflict",
        title: `Conflito de agenda: "${a.title}" e "${b.title}"`,
        reason: `"${a.title}" (${formatDate(a.starts_at)}) sobrepõe "${b.title}" (${formatDate(b.starts_at)})${assumedNote}.`,
        confidence: aAssumed || bAssumed ? "medium" : "high",
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
      category: "recent_change",
      title: `${label}: ${previousList.length} → ${currentList.length}`,
      reason: `Mudou desde a última atualização (${delta > 0 ? "+" : ""}${delta}).`,
      confidence: "high",
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
      category: "follow_up",
      title: `Aprovar meta: ${goal.title}`,
      reason: "Criada com requires_approval — precisa da sua decisão antes de começar.",
      confidence: "high",
      severity: "attention",
      action: { label: "Aprovar", kind: "approve_goal", targetId: goal.id },
    });
  }

  // --- Risk: failed jobs -------------------------------------------------------
  for (const job of input.failedJobs) {
    insights.push({
      id: `retry-${job.id}`,
      category: "risk",
      title: `Job falhou: ${job.name}`,
      reason: job.last_error
        ? `Esgotou as tentativas (${job.attempts}/${job.max_attempts}): ${job.last_error}`
        : `Esgotou as tentativas (${job.attempts}/${job.max_attempts}).`,
      confidence: "high",
      severity: "urgent",
      action: { label: "Tentar novamente", kind: "retry_job", targetId: job.id },
    });
  }

  // --- Missed tasks: overdue -----------------------------------------------------
  for (const task of input.tasks) {
    if (task.status !== "pending") continue;
    if (isOverdue(task.due_date, now)) {
      insights.push({
        id: `missed-${task.id}`,
        category: "missed_task",
        title: `Tarefa atrasada: ${task.title}`,
        reason: `Venceu em ${formatDate(task.due_date as string)} (prioridade ${PRIORITY_LABEL[task.priority] ?? task.priority}).`,
        confidence: "high",
        severity: "attention",
      });
    } else if (isDueSoon(task.due_date, now, 48)) {
      insights.push({
        id: `followup-task-${task.id}`,
        category: "follow_up",
        title: `Vence em breve: ${task.title}`,
        reason: `Prazo ${formatDate(task.due_date as string)} — ainda não vencida, mas dentro de 48h.`,
        confidence: "high",
        severity: "info",
      });
    }
  }

  // --- Highest priority: top ready goals + at-risk goals nearing deadline --------
  const topGoals = input.readyGoals.slice(0, 3);
  for (const goal of topGoals) {
    insights.push({
      id: `priority-goal-${goal.id}`,
      category: "highest_priority",
      title: goal.title,
      reason: `Prioridade ${PRIORITY_LABEL[goal.priority] ?? goal.priority}, ${goal.progress_percent}% concluída${
        goal.deadline ? `, prazo ${formatDate(goal.deadline)}` : ""
      } — próxima na fila por pontuação de urgência.`,
      confidence: "high",
      severity: goal.priority === "urgent" ? "urgent" : "attention",
    });
  }

  // --- Risk: goal deadline close but low progress ---------------------------------
  for (const goal of input.readyGoals) {
    if (!goal.deadline) continue;
    const daysLeft = (new Date(goal.deadline).getTime() - now.getTime()) / 86_400_000;
    if (daysLeft >= 0 && daysLeft <= 3 && goal.progress_percent < 50) {
      insights.push({
        id: `risk-goal-${goal.id}`,
        category: "risk",
        title: `Meta em risco: ${goal.title}`,
        reason: `Prazo em ${Math.ceil(daysLeft)} dia(s), mas só ${goal.progress_percent}% concluída.`,
        confidence: "medium",
        severity: "attention",
      });
    }
  }

  // --- Calendar conflicts ------------------------------------------------------
  insights.push(...findCalendarConflicts(input.calendarEvents));

  // --- Risk: WhatsApp disconnected -----------------------------------------------
  if (input.whatsappConnected === false) {
    insights.push({
      id: "risk-whatsapp",
      category: "risk",
      title: "WhatsApp desconectado",
      reason: "A sessão precisa ser reconectada (QR code no gateway) para o Dario OS continuar respondendo mensagens.",
      confidence: "high",
      severity: "urgent",
    });
  }

  // --- Risk: degraded observation sources -----------------------------------------
  if (input.context && input.context.degraded_sources.length > 0) {
    insights.push({
      id: "risk-observation-degraded",
      category: "risk",
      title: "Observação do sistema incompleta",
      reason: `Fontes indisponíveis na última leitura: ${input.context.degraded_sources.join(", ")}.`,
      confidence: "high",
      severity: "attention",
    });
  }

  // --- Opportunity: a goal close to done -----------------------------------------
  for (const goal of input.readyGoals) {
    if (goal.progress_percent >= 80) {
      insights.push({
        id: `opportunity-goal-${goal.id}`,
        category: "opportunity",
        title: `Quase lá: ${goal.title}`,
        reason: `${goal.progress_percent}% concluída — pode dar para terminar hoje.`,
        confidence: "medium",
        severity: "info",
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
      category: "opportunity",
      title: "Nenhum pendente urgente agora",
      reason: "Sem job falhado, meta aguardando aprovação ou tarefa atrasada — bom momento para avançar a próxima meta ou revisar o backlog.",
      confidence: "medium",
      severity: "info",
    });
  }

  // --- Automatable: already-recurring goals + the system's own background work --
  for (const goal of input.readyGoals) {
    if (goal.recurrence_interval_days) {
      insights.push({
        id: `automatable-goal-${goal.id}`,
        category: "automatable",
        title: `Já automatizada: ${goal.title}`,
        reason: `Recorrente a cada ${goal.recurrence_interval_days} dia(s) — uma nova ocorrência é criada sozinha ao concluir esta.`,
        confidence: "high",
        severity: "info",
      });
    }
  }
  if (input.pendingJobs.length > 0) {
    insights.push({
      id: "automatable-jobs",
      category: "automatable",
      title: `${input.pendingJobs.length} job(s) em andamento automaticamente`,
      reason: "Trabalho em segundo plano já rodando sem intervenção manual (fila de jobs).",
      confidence: "high",
      severity: "info",
    });
  }

  // --- Recently observed changes ------------------------------------------------
  insights.push(...findRecentChanges(input.context, input.previousContext));

  return insights;
}

export function confidenceSummary(insights: OperatorInsight[]): string {
  if (insights.length === 0) return "Nenhuma recomendação no momento.";
  const high = insights.filter((i) => i.confidence === "high").length;
  return `${high} de ${insights.length} recomendações são de alta confiança (baseadas em dados diretos, não inferência).`;
}
