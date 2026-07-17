"use client";

import { useMemo } from "react";
import { Bot, Calendar, ListTodo, MessageCircle, Moon, ShieldAlert, Sparkles, Sun, Sunrise, Target } from "lucide-react";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { BriefingRecommendationCard, AutomationCard } from "@/components/admin/BriefingRecommendationCard";
import { HealthScoreCard } from "@/components/admin/HealthScoreCard";
import { GoalsPanel } from "@/components/admin/GoalsPanel";
import { TasksPanel } from "@/components/admin/TasksPanel";
import { CalendarPanel } from "@/components/admin/CalendarPanel";
import { TimelineEventCard } from "@/components/admin/TimelineEventCard";
import { EmptyState } from "@/components/admin/EmptyState";
import { ErrorState } from "@/components/admin/ErrorState";
import { LoadingRows } from "@/components/admin/LoadingGrid";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import {
  useAdminLogs,
  useAdminObservation,
  useAdminWhatsApp,
  useAllGoals,
  useCalendarEvents,
  useGoalsAwaitingApproval,
  useJobsByStatus,
  useReadyGoals,
  useRecentMessages,
  useTasks,
} from "@/lib/admin-api";
import { useLastLogin } from "@/hooks/use-last-login";
import { buildDailyBriefing } from "@/lib/briefing";
import type { DayPeriod, ExecutionPlanItem } from "@/lib/briefing";
import { filterRange } from "@/lib/timeline";

const PERIOD_LABEL: Record<DayPeriod, string> = { morning: "Manhã", afternoon: "Tarde", evening: "Noite" };
const PERIOD_ICON: Record<DayPeriod, React.ElementType> = { morning: Sunrise, afternoon: Sun, evening: Moon };

function ExecutionPlanColumn({ period, items }: { period: DayPeriod; items: ExecutionPlanItem[] }) {
  const Icon = PERIOD_ICON[period];
  return (
    <div>
      <h3 className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Icon className="h-3.5 w-3.5" /> {PERIOD_LABEL[period]}
      </h3>
      {items.length === 0 ? (
        <p className="text-xs text-muted-foreground">Nada planejado.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item, index) => (
            <li key={index} className="rounded-md border border-border bg-card p-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium">{item.title}</span>
                <span className="shrink-0 text-[11px] text-muted-foreground">
                  {item.estimatedMinutes !== null ? `~${item.estimatedMinutes}min` : "—"}
                </span>
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">{item.reason}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function AdminBriefingPage() {
  const now = useMemo(() => new Date(), []);
  const lastLogin = useLastLogin();

  const readyGoals = useReadyGoals();
  const awaitingApproval = useGoalsAwaitingApproval();
  const allGoals = useAllGoals();
  const tasks = useTasks();
  const calendarEvents = useCalendarEvents();
  const queuedJobs = useJobsByStatus("queued");
  const runningJobs = useJobsByStatus("running");
  const failedJobs = useJobsByStatus("failed");
  const observation = useAdminObservation();
  const whatsapp = useAdminWhatsApp();
  const messages = useRecentMessages(200);
  const baseRange = filterRange("30d", now);
  const logs = useAdminLogs({ since: baseRange.since?.toISOString(), excludeSource: "job:observation.tick", limit: 1000 });

  // Approve-goal and retry-job mutations now live in
  // hooks/use-action-execution.ts, shared with the Operator Center and the
  // Action Center (Phase 4) — see ACTION_CENTER.md.

  const isLoading =
    readyGoals.isLoading ||
    awaitingApproval.isLoading ||
    allGoals.isLoading ||
    tasks.isLoading ||
    calendarEvents.isLoading ||
    queuedJobs.isLoading ||
    runningJobs.isLoading ||
    failedJobs.isLoading ||
    observation.isLoading ||
    whatsapp.isLoading ||
    messages.isLoading ||
    logs.isLoading;

  const firstError =
    readyGoals.error ??
    awaitingApproval.error ??
    allGoals.error ??
    tasks.error ??
    calendarEvents.error ??
    queuedJobs.error ??
    runningJobs.error ??
    failedJobs.error ??
    observation.error ??
    whatsapp.error ??
    messages.error ??
    logs.error;

  const briefing = useMemo(() => {
    if (isLoading || firstError) return null;
    return buildDailyBriefing({
      readyGoals: readyGoals.data ?? [],
      awaitingApprovalGoals: awaitingApproval.data ?? [],
      tasks: tasks.data ?? [],
      calendarEvents: calendarEvents.data ?? [],
      failedJobs: failedJobs.data ?? [],
      pendingJobs: [...(queuedJobs.data ?? []), ...(runningJobs.data ?? [])],
      context: observation.data,
      previousContext: undefined,
      logs: logs.data ?? [],
      messages: messages.data ?? [],
      goals: allGoals.data ?? [],
      now,
      lastLogin,
      whatsappConnected: whatsapp.data?.connected,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    isLoading,
    firstError,
    readyGoals.data,
    awaitingApproval.data,
    tasks.data,
    calendarEvents.data,
    failedJobs.data,
    queuedJobs.data,
    runningJobs.data,
    observation.data,
    logs.data,
    messages.data,
    allGoals.data,
    whatsapp.data,
  ]);

  return (
    <div>
      <AdminPageHeader
        title="Briefing Diário"
        subtitle="O briefing que um assistente executivo prepararia antes do seu dia começar."
      />

      {isLoading ? (
        <LoadingRows count={8} />
      ) : firstError ? (
        <ErrorState message={(firstError as Error).message} />
      ) : !briefing ? null : (
        <>
          {/* Opening narrative — the first thing read, not a metric. */}
          <Card className="mb-6 border-primary/40 bg-primary/5">
            <CardContent className="pt-4">
              <p className="text-base leading-relaxed">{briefing.greeting}</p>
            </CardContent>
          </Card>

          {/* Executive Summary */}
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>Resumo executivo</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-3 text-xs sm:grid-cols-2 lg:grid-cols-3">
                <p><span className="font-medium text-foreground">Mudou durante a noite: </span>{briefing.executiveSummary.changedOvernight}</p>
                <p><span className="font-medium text-foreground">Merece atenção: </span>{briefing.executiveSummary.deservesAttention}</p>
                <p><span className="font-medium text-foreground">Maior oportunidade: </span>{briefing.executiveSummary.biggestOpportunity ?? "Nenhuma no momento."}</p>
                <p><span className="font-medium text-foreground">Maior risco: </span>{briefing.executiveSummary.biggestRisk ?? "Nenhum no momento."}</p>
                <p><span className="font-medium text-foreground">Carga estimada: </span>{briefing.executiveSummary.estimatedWorkloadMinutes > 0 ? `~${briefing.executiveSummary.estimatedWorkloadMinutes}min` : "Leve."}</p>
                <p><span className="font-medium text-foreground">Ordem sugerida: </span>{briefing.executiveSummary.recommendedOrder.slice(0, 3).join(" → ") || "—"}</p>
              </div>
            </CardContent>
          </Card>

          <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
            {/* 🔥 Top Priorities */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5"><Target className="h-4 w-4" /> Prioridades</CardTitle>
              </CardHeader>
              <CardContent>
                {briefing.topPriorities.length === 0 ? (
                  <EmptyState compact title="Nenhuma prioridade urgente" />
                ) : (
                  <ul className="flex flex-col gap-2">
                    {briefing.topPriorities.map((rec) => (
                      <BriefingRecommendationCard key={rec.insight.id} recommendation={rec} />
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            {/* ⚠️ Risks */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5"><ShieldAlert className="h-4 w-4" /> Riscos</CardTitle>
              </CardHeader>
              <CardContent>
                {briefing.risks.length === 0 ? (
                  <EmptyState compact title="Nenhum risco identificado" />
                ) : (
                  <ul className="flex flex-col gap-2">
                    {briefing.risks.map((rec) => (
                      <BriefingRecommendationCard key={rec.insight.id} recommendation={rec} />
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            {/* 💡 Opportunities */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5"><Sparkles className="h-4 w-4" /> Oportunidades</CardTitle>
              </CardHeader>
              <CardContent>
                {briefing.opportunities.length === 0 ? (
                  <EmptyState compact title="Nenhuma oportunidade nova" />
                ) : (
                  <ul className="flex flex-col gap-2">
                    {briefing.opportunities.map((rec) => (
                      <BriefingRecommendationCard key={rec.insight.id} recommendation={rec} />
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Execution Plan */}
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>Plano de execução (sugestão por urgência, não uma agenda imposta)</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                {(["morning", "afternoon", "evening"] as DayPeriod[]).map((period) => (
                  <ExecutionPlanColumn
                    key={period}
                    period={period}
                    items={briefing.executionPlan.filter((i) => i.period === period)}
                  />
                ))}
              </div>
            </CardContent>
          </Card>

          <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* 📅 Today's Calendar */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5"><Calendar className="h-4 w-4" /> Agenda de hoje</CardTitle>
              </CardHeader>
              <CardContent>
                <CalendarPanel events={briefing.todaysCalendar} />
              </CardContent>
            </Card>

            {/* ✅ Today's Tasks */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5"><ListTodo className="h-4 w-4" /> Tarefas de hoje</CardTitle>
              </CardHeader>
              <CardContent>
                <TasksPanel tasks={briefing.todaysTasks} />
              </CardContent>
            </Card>
          </div>

          <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* 📈 Goal Progress */}
            <Card>
              <CardHeader>
                <CardTitle>Progresso de metas</CardTitle>
              </CardHeader>
              <CardContent>
                <GoalsPanel goals={briefing.goalProgress} />
              </CardContent>
            </Card>

            {/* 💬 Recent Conversations */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5"><MessageCircle className="h-4 w-4" /> Conversas recentes</CardTitle>
              </CardHeader>
              <CardContent>
                {briefing.recentConversations.length === 0 ? (
                  <EmptyState compact title="Nenhuma conversa recente" />
                ) : (
                  <ul className="flex flex-col gap-2">
                    {briefing.recentConversations.map((event) => (
                      <TimelineEventCard key={event.id} event={event} />
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
            {/* 🤖 AI Recommendations (automations) */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5"><Bot className="h-4 w-4" /> Recomendações da IA</CardTitle>
              </CardHeader>
              <CardContent>
                {briefing.automations.length === 0 ? (
                  <EmptyState compact title="Nada automatizado a reportar" />
                ) : (
                  <ul className="flex flex-col gap-2">
                    {briefing.automations.map((rec) => (
                      <AutomationCard key={rec.insight.id} recommendation={rec} />
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            {/* 🧠 What Changed Since Yesterday */}
            <Card>
              <CardHeader>
                <CardTitle>O que mudou desde ontem</CardTitle>
              </CardHeader>
              <CardContent>
                {briefing.changedSinceYesterday.totalEvents === 0 ? (
                  <EmptyState compact title="Nada mudou desde ontem" />
                ) : (
                  <p className="text-xs text-muted-foreground">
                    {briefing.changedSinceYesterday.totalEvents} evento(s) —{" "}
                    {Object.entries(briefing.changedSinceYesterday.byCategory)
                      .map(([category, count]) => `${category}: ${count}`)
                      .join(" · ")}
                  </p>
                )}
              </CardContent>
            </Card>

            {/* 📊 Daily Health Score */}
            <Card>
              <CardHeader>
                <CardTitle>Saúde do dia</CardTitle>
              </CardHeader>
              <CardContent>
                <HealthScoreCard health={briefing.healthScore} />
              </CardContent>
            </Card>
          </div>

          {/* Closing line */}
          <Card className="border-primary/40 bg-primary/5">
            <CardContent className="pt-4">
              <p className="text-sm font-medium">{briefing.closingLine}</p>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
