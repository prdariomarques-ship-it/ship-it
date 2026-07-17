// Daily Briefing — composes lib/operator.ts (priorities/risks/opportunities/
// automations, each with why/confidence/impact/time already built) and
// lib/timeline.ts ("what changed") into a single narrative document: an
// opening paragraph, an executive summary, an execution plan for the day,
// an explainable health score, and a closing "do this one thing" line.
// Every number here is either a real count from real data or a fixed,
// documented deduction/estimate — never an LLM guess. See DAILY_BRIEFING.md.

import type { CalendarEventRead, GoalRead, TaskRead } from "@/lib/admin-types";
import type { OperatorInput, OperatorInsight } from "@/lib/operator";
import { buildOperatorInsights } from "@/lib/operator";
import type { ChangeSummary, TimelineEvent, TimelineInput } from "@/lib/timeline";
import { buildTimelineEvents, filterRange, summarizeChanges } from "@/lib/timeline";

export interface BriefingRecommendation {
  insight: OperatorInsight;
  whyNow: string;
  consequenceIfIgnored: string;
}

export interface HealthDeduction {
  label: string;
  points: number;
  reason: string;
}

export interface DailyHealthScore {
  score: number;
  deductions: HealthDeduction[];
  formula: string;
}

export type DayPeriod = "morning" | "afternoon" | "evening";

export interface ExecutionPlanItem {
  period: DayPeriod;
  title: string;
  estimatedMinutes: number | null;
  reason: string;
  expectedImpact: string;
}

export interface ExecutiveSummary {
  changedOvernight: string;
  deservesAttention: string;
  biggestOpportunity: string | null;
  biggestRisk: string | null;
  estimatedWorkloadMinutes: number;
  recommendedOrder: string[];
}

export interface DailyBriefing {
  greeting: string;
  executiveSummary: ExecutiveSummary;
  topPriorities: BriefingRecommendation[];
  risks: BriefingRecommendation[];
  opportunities: BriefingRecommendation[];
  automations: BriefingRecommendation[];
  todaysCalendar: CalendarEventRead[];
  calendarConflicts: OperatorInsight[];
  todaysTasks: TaskRead[];
  goalProgress: GoalRead[];
  recentConversations: TimelineEvent[];
  changedSinceYesterday: ChangeSummary;
  changedSinceLastLogin: ChangeSummary | null;
  healthScore: DailyHealthScore;
  executionPlan: ExecutionPlanItem[];
  closingLine: string;
}

export interface BriefingInput extends OperatorInput, TimelineInput {
  now: Date;
  lastLogin: Date | null;
  whatsappConnected: boolean | undefined;
}

// --- Decision support: why-now / consequence-if-ignored, one rule per category —
// same "explainable, not fabricated per-instance" discipline as everything else
// in this codebase. Two insights in the same category get the same *kind* of
// answer because the underlying situation really is the same kind of situation. ---
function whyNow(insight: OperatorInsight): string {
  switch (insight.category) {
    case "missed_task":
      return "Já está atrasada — cada dia a mais reduz a chance de ser feita.";
    case "follow_up":
      return "Uma decisão sua é o único passo faltando para destravar isso.";
    case "calendar_conflict":
      return "Os dois compromissos coincidem — decidir agora evita escolher às pressas na hora.";
    case "risk":
      return insight.severity === "urgent"
        ? "Já passou do ponto ideal de ação."
        : "Ainda dá para agir antes de virar urgência.";
    case "highest_priority":
      return "É a meta com maior pontuação de urgência na fila agora.";
    case "opportunity":
      return "A janela existe hoje; nada garante que continue amanhã.";
    case "automatable":
      return "Não precisa da sua atenção — já está resolvido.";
    default:
      return insight.reason;
  }
}

function consequenceIfIgnored(insight: OperatorInsight): string {
  switch (insight.category) {
    case "missed_task":
      return "Risco real de a tarefa ser esquecida e o prazo original perdido de vez.";
    case "follow_up":
      return "A meta continua fora da fila de execução.";
    case "calendar_conflict":
      return "Um dos dois compromissos será perdido ou remarcado às pressas.";
    case "risk":
      return insight.severity === "urgent"
        ? "O problema tende a se agravar sem intervenção."
        : "Vira urgência nos próximos dias.";
    case "highest_priority":
      return "A meta fica mais tempo parada na fila.";
    case "opportunity":
      return "A oportunidade pode não estar mais disponível depois.";
    case "automatable":
      return "Nenhuma — já está sendo cuidado automaticamente.";
    default:
      return "Nenhuma ação necessária.";
  }
}

function toRecommendation(insight: OperatorInsight): BriefingRecommendation {
  return { insight, whyNow: whyNow(insight), consequenceIfIgnored: consequenceIfIgnored(insight) };
}

// --- Health Score: starts at 100, each deduction fixed and itemized — the
// exact six factors named in the brief, none double-counted. ------------------
function computeHealthScore(input: {
  overdueTasks: number;
  atRiskGoals: number;
  calendarConflicts: number;
  awaitingApprovalGoals: number;
  whatsappConnected: boolean | undefined;
  degradedSources: number;
  failedJobs: number;
}): DailyHealthScore {
  const deductions: HealthDeduction[] = [];

  if (input.overdueTasks > 0) {
    deductions.push({
      label: "Tarefas atrasadas",
      points: Math.min(input.overdueTasks * 5, 25),
      reason: `${input.overdueTasks} tarefa(s) vencida(s) e ainda pendente(s).`,
    });
  }
  if (input.atRiskGoals > 0) {
    deductions.push({
      label: "Progresso de metas",
      points: Math.min(input.atRiskGoals * 10, 20),
      reason: `${input.atRiskGoals} meta(s) com prazo próximo e progresso baixo.`,
    });
  }
  if (input.calendarConflicts > 0) {
    deductions.push({
      label: "Conflitos de agenda",
      points: Math.min(input.calendarConflicts * 15, 30),
      reason: `${input.calendarConflicts} conflito(s) de horário detectado(s) hoje.`,
    });
  }
  if (input.awaitingApprovalGoals > 0) {
    deductions.push({
      label: "Follow-ups não resolvidos",
      points: Math.min(input.awaitingApprovalGoals * 8, 24),
      reason: `${input.awaitingApprovalGoals} meta(s) aguardando sua aprovação.`,
    });
  }
  if (input.whatsappConnected === false) {
    deductions.push({ label: "Saúde do sistema", points: 20, reason: "WhatsApp desconectado." });
  }
  if (input.degradedSources > 0) {
    deductions.push({
      label: "Saúde do sistema",
      points: Math.min(input.degradedSources * 10, 20),
      reason: `${input.degradedSources} fonte(s) de observação indisponível(is).`,
    });
  }
  if (input.failedJobs > 0) {
    deductions.push({
      label: "Ações pendentes",
      points: Math.min(input.failedJobs * 10, 30),
      reason: `${input.failedJobs} job(s) falhado(s) precisando de nova tentativa.`,
    });
  }

  const totalDeduction = deductions.reduce((sum, d) => sum + d.points, 0);
  const score = Math.max(0, 100 - totalDeduction);
  const formula =
    deductions.length === 0
      ? "100 (nenhum problema detectado)"
      : `100 - ${deductions.map((d) => d.points).join(" - ")} = ${score}`;

  return { score, deductions, formula };
}

// --- Execution Plan: calendar events go where they're actually scheduled;
// everything else is ordered by urgency into Morning first (an assistant
// front-loads the hard things), then Afternoon, then Evening. This is a
// suggested order, not a scheduling optimizer — said explicitly in the UI. --
function periodForHour(hour: number): DayPeriod {
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}

function buildExecutionPlan(
  todaysCalendar: CalendarEventRead[],
  urgentRecs: BriefingRecommendation[],
  todayRecs: BriefingRecommendation[]
): ExecutionPlanItem[] {
  const plan: ExecutionPlanItem[] = [];

  for (const event of todaysCalendar) {
    plan.push({
      // UTC, not local time — consistent with startOfDay/filterRange and
      // every other date boundary in this codebase (see lib/timeline.ts).
      period: periodForHour(new Date(event.starts_at).getUTCHours()),
      title: event.title,
      estimatedMinutes:
        event.ends_at != null
          ? Math.round((new Date(event.ends_at).getTime() - new Date(event.starts_at).getTime()) / 60_000)
          : null,
      reason: "Compromisso agendado neste horário.",
      expectedImpact: "Presença confirmada no compromisso.",
    });
  }

  // Non-calendar work: urgent items front-loaded to the morning, today-bucket
  // items to the afternoon — a suggestion, not an imposed schedule.
  for (const rec of urgentRecs) {
    plan.push({
      period: "morning",
      title: rec.insight.title,
      estimatedMinutes: rec.insight.estimatedMinutes,
      reason: rec.whyNow,
      expectedImpact: rec.insight.impact,
    });
  }
  for (const rec of todayRecs) {
    plan.push({
      period: "afternoon",
      title: rec.insight.title,
      estimatedMinutes: rec.insight.estimatedMinutes,
      reason: rec.whyNow,
      expectedImpact: rec.insight.impact,
    });
  }

  const order: Record<DayPeriod, number> = { morning: 0, afternoon: 1, evening: 2 };
  return plan.sort((a, b) => order[a.period] - order[b.period]);
}

function startOfDay(date: Date): Date {
  const d = new Date(date);
  d.setUTCHours(0, 0, 0, 0);
  return d;
}

export function buildDailyBriefing(input: BriefingInput): DailyBriefing {
  const insights = buildOperatorInsights(input);
  const events = buildTimelineEvents(
    { logs: input.logs, messages: input.messages, goals: input.goals, tasks: input.tasks, calendarEvents: input.calendarEvents },
    filterRange("30d", input.now).since
  );

  const today = startOfDay(input.now);
  const tomorrow = new Date(today.getTime() + 86_400_000);
  const todaysCalendar = input.calendarEvents
    .filter((e) => {
      const t = new Date(e.starts_at).getTime();
      return t >= today.getTime() && t < tomorrow.getTime();
    })
    .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime());

  const todaysTasks = input.tasks
    .filter((t) => t.status === "pending")
    .filter((t) => !t.due_date || new Date(t.due_date).getTime() < tomorrow.getTime())
    .sort((a, b) => {
      if (!a.due_date) return 1;
      if (!b.due_date) return -1;
      return new Date(a.due_date).getTime() - new Date(b.due_date).getTime();
    });

  const overdueTasks = todaysTasks.filter((t) => t.due_date && new Date(t.due_date).getTime() < input.now.getTime());

  const urgentInsights = insights.filter((i) => i.bucket === "urgent" && i.category !== "recent_change");
  const todayInsights = insights.filter((i) => i.bucket === "today" && i.category !== "recent_change");
  const opportunityInsights = insights.filter((i) => i.bucket === "opportunity");
  const automationInsights = insights.filter((i) => i.bucket === "automation");
  const conflictInsights = insights.filter((i) => i.category === "calendar_conflict");
  const riskInsights = insights.filter((i) => i.category === "risk" || i.category === "missed_task");
  const priorityInsights = [...urgentInsights, ...todayInsights].slice(0, 5);

  const topPriorities = priorityInsights.map(toRecommendation);
  const risks = riskInsights.map(toRecommendation);
  const opportunities = opportunityInsights.map(toRecommendation);
  const automations = automationInsights.map(toRecommendation);

  const changedSinceYesterday = summarizeChanges(events, filterRange("yesterday", input.now).since as Date, "Desde ontem");
  const changedSinceLastLogin = input.lastLogin
    ? summarizeChanges(events, input.lastLogin, "Desde seu último login")
    : null;

  const atRiskGoals = input.goals.filter((g) => {
    if (!g.deadline) return false;
    const daysLeft = (new Date(g.deadline).getTime() - input.now.getTime()) / 86_400_000;
    return daysLeft >= 0 && daysLeft <= 3 && g.progress_percent < 50;
  }).length;

  const healthScore = computeHealthScore({
    overdueTasks: overdueTasks.length,
    atRiskGoals,
    calendarConflicts: conflictInsights.length,
    awaitingApprovalGoals: input.awaitingApprovalGoals.length,
    whatsappConnected: input.whatsappConnected,
    degradedSources: input.context?.degraded_sources.length ?? 0,
    failedJobs: input.failedJobs.length,
  });

  const workloadMinutes = [...topPriorities, ...risks]
    .map((r) => r.insight.estimatedMinutes ?? 0)
    .reduce((sum, m) => sum + m, 0);

  const topInsight = priorityInsights[0] ?? riskInsights[0] ?? null;

  const executiveSummary: ExecutiveSummary = {
    changedOvernight:
      changedSinceYesterday.totalEvents === 0
        ? "Nada de novo desde ontem."
        : `${changedSinceYesterday.totalEvents} evento(s) desde ontem.`,
    deservesAttention: topInsight ? topInsight.title : "Nada exige atenção imediata.",
    biggestOpportunity: opportunityInsights[0]?.title ?? null,
    biggestRisk: riskInsights[0]?.title ?? null,
    estimatedWorkloadMinutes: workloadMinutes,
    recommendedOrder: priorityInsights.map((i) => i.title),
  };

  const executionPlan = buildExecutionPlan(
    todaysCalendar,
    urgentInsights.map(toRecommendation),
    todayInsights.map(toRecommendation)
  );

  const workloadLabel =
    workloadMinutes > 0
      ? `Concluir as prioridades de hoje deve levar aproximadamente ${
          workloadMinutes >= 60 ? `${Math.floor(workloadMinutes / 60)}h${workloadMinutes % 60 || ""}` : `${workloadMinutes}min`
        }.`
      : "";

  const greetingParts = [
    `Hoje há ${topPriorities.length} prioridade(s) que merece(m) sua atenção.`,
    overdueTasks.length > 0
      ? `${overdueTasks.length} tarefa(s) importante(s) está(ão) atrasada(s).`
      : "Nenhum follow-up importante está atrasado.",
    conflictInsights.length > 0
      ? `Há ${conflictInsights.length} conflito(s) de agenda hoje.`
      : "Não há conflitos de agenda.",
    input.whatsappConnected === false ? "O WhatsApp está desconectado." : "O WhatsApp está saudável.",
    opportunityInsights.length > 0
      ? `${opportunityInsights.length} oportunidade(s) foram detectadas.`
      : "Nenhuma oportunidade nova detectada.",
    workloadLabel,
  ].filter(Boolean);

  const greeting = greetingParts.join(" ");

  const closingLine = topInsight
    ? `Se você só puder fazer uma coisa hoje, que seja: ${topInsight.title}.`
    : "Se você só puder fazer uma coisa hoje: revisar as oportunidades abaixo — não há nada urgente pendente.";

  return {
    greeting,
    executiveSummary,
    topPriorities,
    risks,
    opportunities,
    automations,
    todaysCalendar,
    calendarConflicts: conflictInsights,
    todaysTasks,
    goalProgress: input.readyGoals,
    recentConversations: events.filter((e) => e.category === "recent_conversations").slice(0, 5),
    changedSinceYesterday,
    changedSinceLastLogin,
    healthScore,
    executionPlan,
    closingLine,
  };
}
