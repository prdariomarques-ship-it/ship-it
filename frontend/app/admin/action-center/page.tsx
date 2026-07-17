"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  Clock3,
  Hourglass,
  ListChecks,
  Loader2,
  ShieldQuestion,
  Timer,
  XCircle,
} from "lucide-react";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { ActionWorkflowControl } from "@/components/admin/ActionWorkflowControl";
import { MetricCard } from "@/components/admin/MetricCard";
import { EmptyState } from "@/components/admin/EmptyState";
import { ErrorState } from "@/components/admin/ErrorState";
import { LoadingRows } from "@/components/admin/LoadingGrid";
import { Badge } from "@/components/admin/ui/badge";
import { Button } from "@/components/admin/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import {
  useAdminLogs,
  useAdminObservation,
  useAdminWhatsApp,
  useCalendarEvents,
  useGoalsAwaitingApproval,
  useJobsByStatus,
  useReadyGoals,
  useTasks,
} from "@/lib/admin-api";
import { useOperatorInsightState } from "@/hooks/use-operator-state";
import { useActionExecution } from "@/hooks/use-action-execution";
import { buildOperatorInsights } from "@/lib/operator";
import type { OperatorInsight } from "@/lib/operator";
import { computeAutomationScore, parseActionLog, planAction } from "@/lib/actions";
import type { ActionLogItem, ActionPlan } from "@/lib/actions";

const ACTION_LOG_LIMIT = 200;

function InsightWorkflowItem({ insight }: { insight: OperatorInsight }) {
  return (
    <li className="flex flex-col gap-2 rounded-md border border-border bg-card p-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="text-sm font-medium">{insight.title}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{insight.reason}</p>
      </div>
      <ActionWorkflowControl insight={insight} />
    </li>
  );
}

function ManualOnlyItem({ insight, plan }: { insight: OperatorInsight; plan: ActionPlan }) {
  return (
    <li className="flex flex-col gap-2 rounded-md border border-border bg-card p-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="text-sm font-medium">{insight.title}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Por que não é automático: </span>
          {plan.classificationReason}
        </p>
      </div>
      <Button variant="ghost" size="sm" asChild>
        <Link href={plan.url ?? "/admin"}>{plan.actionLabel}</Link>
      </Button>
    </li>
  );
}

function LogItem({ log, tone }: { log: ActionLogItem; tone: "success" | "destructive" }) {
  return (
    <li className="rounded-md border border-border bg-card p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-sm font-medium">{log.recommendationTitle}</span>
        <Badge variant={tone}>{tone === "success" ? "concluída" : "falhou"}</Badge>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {new Date(log.createdAt).toLocaleString("pt-BR")}
        {log.relatedEntities.length > 0 ? ` — ${log.relatedEntities.join(", ")}` : ""}
        {log.estimatedMinutes !== null ? ` — ~${log.estimatedMinutes}min` : ""}
      </p>
      {log.detail ? <p className="mt-0.5 text-xs text-destructive">{log.detail}</p> : null}
    </li>
  );
}

export default function ActionCenterPage() {
  const now = useMemo(() => new Date(), []);
  const readyGoals = useReadyGoals();
  const awaitingApproval = useGoalsAwaitingApproval();
  const tasks = useTasks();
  const calendarEvents = useCalendarEvents();
  const queuedJobs = useJobsByStatus("queued");
  const runningJobs = useJobsByStatus("running");
  const failedJobs = useJobsByStatus("failed");
  const observation = useAdminObservation();
  const whatsapp = useAdminWhatsApp();
  const actionLogs = useAdminLogs({ sourcePrefix: "admin:action.", limit: ACTION_LOG_LIMIT });

  const { isHidden } = useOperatorInsightState();
  const { isExecuting } = useActionExecution();

  const isLoading =
    readyGoals.isLoading ||
    awaitingApproval.isLoading ||
    tasks.isLoading ||
    calendarEvents.isLoading ||
    queuedJobs.isLoading ||
    runningJobs.isLoading ||
    failedJobs.isLoading ||
    observation.isLoading ||
    whatsapp.isLoading ||
    actionLogs.isLoading;

  const firstError =
    readyGoals.error ??
    awaitingApproval.error ??
    tasks.error ??
    calendarEvents.error ??
    queuedJobs.error ??
    runningJobs.error ??
    failedJobs.error ??
    observation.error ??
    whatsapp.error ??
    actionLogs.error;

  const insights = useMemo(() => {
    if (isLoading || firstError) return [];
    return buildOperatorInsights({
      readyGoals: readyGoals.data ?? [],
      awaitingApprovalGoals: awaitingApproval.data ?? [],
      tasks: tasks.data ?? [],
      calendarEvents: calendarEvents.data ?? [],
      failedJobs: failedJobs.data ?? [],
      pendingJobs: [...(queuedJobs.data ?? []), ...(runningJobs.data ?? [])],
      context: observation.data,
      previousContext: undefined,
      whatsappConnected: whatsapp.data?.connected,
      now,
    }).filter((insight) => insight.category !== "recent_change" && !isHidden(insight.id));
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
    whatsapp.data,
    now,
  ]);

  const pending: OperatorInsight[] = [];
  const waitingConfirmation: OperatorInsight[] = [];
  const manualOnly: { insight: OperatorInsight; plan: ActionPlan }[] = [];

  for (const insight of insights) {
    const plan = planAction(insight);
    if (!plan) continue;
    if (plan.classification === "SAFE_AUTOMATIC") pending.push(insight);
    else if (plan.classification === "REQUIRES_CONFIRMATION") waitingConfirmation.push(insight);
    else manualOnly.push({ insight, plan });
  }

  const parsedLogs = (actionLogs.data ?? [])
    .map(parseActionLog)
    .filter((item): item is ActionLogItem => item !== null);
  const completed = parsedLogs.filter((l) => l.result === "success");
  const failed = parsedLogs.filter((l) => l.result === "failure");

  const runningCount = insights.filter((insight) => {
    const plan = planAction(insight);
    return plan ? isExecuting(plan.actionKind, plan.targetId) : false;
  }).length;

  const score = computeAutomationScore(actionLogs.data ?? [], waitingConfirmation.length, now);

  return (
    <div>
      <AdminPageHeader
        title="Central de Ações"
        subtitle="Cada recomendação vira um workflow executável — a menor quantidade de cliques possível, sempre com o resultado registrado na Timeline."
      />

      {isLoading ? (
        <LoadingRows count={8} />
      ) : firstError ? (
        <ErrorState message={(firstError as Error).message} />
      ) : (
        <>
          {/* Automation Score — every number here comes from real /admin/actions/log
              entries or a real-time count, never a fabricated estimate. */}
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="Ações concluídas hoje" value={score.actionsCompletedToday} icon={ListChecks} tone="success" />
            <MetricCard label="Minutos economizados hoje" value={score.estimatedMinutesSavedToday} icon={Timer} />
            <MetricCard label="Operações manuais evitadas hoje" value={score.manualStepsAvoidedToday} icon={CheckCircle2} />
            <MetricCard label="Confirmações pendentes" value={score.pendingConfirmations} icon={Hourglass} tone={score.pendingConfirmations > 0 ? "warning" : "default"} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Pending — SAFE_AUTOMATIC, one click away. */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5"><Clock3 className="h-4 w-4" /> Pendentes ({pending.length})</CardTitle>
              </CardHeader>
              <CardContent>
                {pending.length === 0 ? (
                  <EmptyState compact title="Nada pendente" description="Sem ações seguras aguardando execução." />
                ) : (
                  <ul className="flex flex-col gap-2">
                    {pending.map((insight) => (
                      <InsightWorkflowItem key={insight.id} insight={insight} />
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            {/* Waiting for confirmation — REQUIRES_CONFIRMATION. */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5"><ShieldQuestion className="h-4 w-4" /> Aguardando confirmação ({waitingConfirmation.length})</CardTitle>
              </CardHeader>
              <CardContent>
                {waitingConfirmation.length === 0 ? (
                  <EmptyState compact title="Nada aguardando confirmação" />
                ) : (
                  <ul className="flex flex-col gap-2">
                    {waitingConfirmation.map((insight) => (
                      <InsightWorkflowItem key={insight.id} insight={insight} />
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            {/* Running — real mutation state, not simulated. Every action here
                is a synchronous HTTP call, so this is almost always empty;
                see ACTION_CENTER.md "Known limitations". */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5"><Loader2 className="h-4 w-4" /> Em execução ({runningCount})</CardTitle>
              </CardHeader>
              <CardContent>
                {runningCount === 0 ? (
                  <EmptyState compact title="Nada em execução agora" description="Ações são chamadas HTTP síncronas — normalmente concluem antes de aparecer aqui." />
                ) : (
                  <ul className="flex flex-col gap-2">
                    {insights
                      .filter((insight) => {
                        const plan = planAction(insight);
                        return plan ? isExecuting(plan.actionKind, plan.targetId) : false;
                      })
                      .map((insight) => (
                        <li key={insight.id} className="rounded-md border border-border bg-card p-3 text-sm">
                          {insight.title}
                        </li>
                      ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            {/* Manual only — honest about what the system can't do for you. */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5"><XCircle className="h-4 w-4" /> Requer ação manual ({manualOnly.length})</CardTitle>
              </CardHeader>
              <CardContent>
                {manualOnly.length === 0 ? (
                  <EmptyState compact title="Nada manual pendente" />
                ) : (
                  <ul className="flex flex-col gap-2">
                    {manualOnly.map(({ insight, plan }) => (
                      <ManualOnlyItem key={insight.id} insight={insight} plan={plan} />
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Completed */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5"><CheckCircle2 className="h-4 w-4" /> Concluídas ({completed.length})</CardTitle>
              </CardHeader>
              <CardContent>
                {completed.length === 0 ? (
                  <EmptyState compact title="Nenhuma ação concluída ainda" />
                ) : (
                  <ul className="flex flex-col gap-2">
                    {completed.slice(0, 20).map((log) => (
                      <LogItem key={log.id} log={log} tone="success" />
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            {/* Failed */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5"><XCircle className="h-4 w-4" /> Falhadas ({failed.length})</CardTitle>
              </CardHeader>
              <CardContent>
                {failed.length === 0 ? (
                  <EmptyState compact title="Nenhuma falha registrada" />
                ) : (
                  <ul className="flex flex-col gap-2">
                    {failed.slice(0, 20).map((log) => (
                      <LogItem key={log.id} log={log} tone="destructive" />
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
