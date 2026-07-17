"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Bot,
  Clock,
  MessageCircle,
  ShieldCheck,
  Users,
  Wrench,
} from "lucide-react";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { StatusCard } from "@/components/admin/StatusCard";
import { MetricCard } from "@/components/admin/MetricCard";
import { MetricChart } from "@/components/admin/charts/MetricChart";
import { LoadingGrid, LoadingRows } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { CurrentContextPanel } from "@/components/admin/CurrentContextPanel";
import { GoalsPanel } from "@/components/admin/GoalsPanel";
import { TasksPanel } from "@/components/admin/TasksPanel";
import { CalendarPanel } from "@/components/admin/CalendarPanel";
import { SuggestedActionsPanel } from "@/components/admin/SuggestedActionsPanel";
import { PendingJobsPanel } from "@/components/admin/PendingJobsPanel";
import { PipelineActivityPanel } from "@/components/admin/PipelineActivityPanel";
import { LogViewer } from "@/components/admin/LogViewer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import {
  useAdminIndex,
  useAdminLogs,
  useAdminMetrics,
  useAdminObservation,
  useAdminStatus,
  useAdminWhatsApp,
  useCalendarEvents,
  useGoalsAwaitingApproval,
  useJobsByStatus,
  useReadyGoals,
  useTasks,
} from "@/lib/admin-api";
import { useRatePerMinute } from "@/hooks/use-rolling-series";
import { useToast } from "@/hooks/use-toast";
import { apiFetch } from "@/hooks/useApi";
import { sumMetric } from "@/lib/metrics-helpers";
import { formatNumber, formatUptime } from "@/lib/format";

const FRONTEND_STATUS = {
  name: "frontend",
  online: true,
  detail: "você está usando agora",
  latency_ms: 0,
  last_heartbeat: new Date().toISOString(),
};

function endOfToday(): number {
  const date = new Date();
  date.setHours(23, 59, 59, 999);
  return date.getTime();
}

export default function AdminDashboardPage() {
  const index = useAdminIndex();
  const status = useAdminStatus();
  const metrics = useAdminMetrics();
  const whatsapp = useAdminWhatsApp();
  const observation = useAdminObservation();
  const readyGoals = useReadyGoals();
  const awaitingApproval = useGoalsAwaitingApproval();
  const tasks = useTasks();
  const calendar = useCalendarEvents();
  const queuedJobs = useJobsByStatus("queued");
  const runningJobs = useJobsByStatus("running");
  const failedJobs = useJobsByStatus("failed");
  const recentLogs = useAdminLogs({ limit: 15 });
  const pipelineLogs = useAdminLogs({ source: "cognitive_pipeline", limit: 10 });

  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [logLevel, setLogLevel] = useState<string | undefined>(undefined);
  const [logSearch, setLogSearch] = useState("");

  const executionsTotal = sumMetric(metrics.data, "darioos_agent_runs_total");
  const errorsTotal = sumMetric(metrics.data, "darioos_agent_runs_total", { status: "error" });
  const tokensTotal =
    sumMetric(metrics.data, "darioos_agent_tokens_total", { kind: "prompt" }) +
    sumMetric(metrics.data, "darioos_agent_tokens_total", { kind: "completion" });
  const httpDurationSum = sumMetric(metrics.data, "darioos_http_request_duration_seconds_sum");
  const httpDurationCount = sumMetric(metrics.data, "darioos_http_request_duration_seconds_count");
  const avgLatencyMs = httpDurationCount > 0 ? (httpDurationSum / httpDurationCount) * 1000 : null;

  const executionsSeries = useRatePerMinute(executionsTotal);
  const errorsSeries = useRatePerMinute(errorsTotal);
  const tokensSeries = useRatePerMinute(tokensTotal);
  const latencySeries = useRatePerMinute(avgLatencyMs);

  const todaysTasks = useMemo(() => {
    const deadline = endOfToday();
    return (tasks.data ?? [])
      .filter((task) => task.status === "pending")
      .filter((task) => !task.due_date || new Date(task.due_date).getTime() <= deadline)
      .sort((a, b) => {
        if (!a.due_date) return 1;
        if (!b.due_date) return -1;
        return new Date(a.due_date).getTime() - new Date(b.due_date).getTime();
      });
  }, [tasks.data]);

  const overdueTasks = useMemo(
    () => todaysTasks.filter((task) => task.due_date && new Date(task.due_date).getTime() < Date.now()),
    [todaysTasks]
  );

  const upcomingEvents = useMemo(() => {
    const now = Date.now();
    return (calendar.data ?? [])
      .filter((event) => new Date(event.starts_at).getTime() >= now)
      .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime())
      .slice(0, 8);
  }, [calendar.data]);

  const pendingJobs = useMemo(
    () => [...(queuedJobs.data ?? []), ...(runningJobs.data ?? [])],
    [queuedJobs.data, runningJobs.data]
  );

  const [approvingGoalId, setApprovingGoalId] = useState<number | null>(null);
  const [retryingJobId, setRetryingJobId] = useState<number | null>(null);
  const [cancelingJobId, setCancelingJobId] = useState<number | null>(null);

  const approveGoal = useMutation({
    mutationFn: (goalId: number) => apiFetch(`/goals/${goalId}/approve`, { method: "POST" }),
    onMutate: (goalId) => setApprovingGoalId(goalId),
    onSuccess: () => {
      toast({ title: "Meta aprovada", variant: "success" });
      queryClient.invalidateQueries({ queryKey: ["goals"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "observation"] });
    },
    onError: (error: Error) => toast({ title: "Falha ao aprovar meta", description: error.message, variant: "destructive" }),
    onSettled: () => setApprovingGoalId(null),
  });

  const retryJob = useMutation({
    mutationFn: (jobId: number) => apiFetch(`/admin/jobs/${jobId}/retry`, { method: "POST" }),
    onMutate: (jobId) => setRetryingJobId(jobId),
    onSuccess: () => {
      toast({ title: "Job reenviado para a fila", variant: "success" });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error: Error) => toast({ title: "Falha ao reenviar job", description: error.message, variant: "destructive" }),
    onSettled: () => setRetryingJobId(null),
  });

  const cancelJob = useMutation({
    mutationFn: (jobId: number) => apiFetch(`/admin/jobs/${jobId}/cancel`, { method: "POST" }),
    onMutate: (jobId) => setCancelingJobId(jobId),
    onSuccess: () => {
      toast({ title: "Job cancelado", variant: "success" });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error: Error) => toast({ title: "Falha ao cancelar job", description: error.message, variant: "destructive" }),
    onSettled: () => setCancelingJobId(null),
  });

  return (
    <div>
      <AdminPageHeader
        title="Dashboard"
        subtitle="Operação do Dario OS inteira, em uma tela: contexto atual, metas, tarefas, agenda, WhatsApp, jobs e atividade do Cognitive Pipeline."
      />

      {/* Panel 9: System Health */}
      <section className="mb-8">
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Status dos sistemas</h2>
        {status.isLoading ? (
          <LoadingGrid count={9} />
        ) : status.isError ? (
          <ErrorState message={(status.error as Error).message} onRetry={() => status.refetch()} />
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
          >
            <StatusCard status={FRONTEND_STATUS} />
            {status.data?.map((item) => <StatusCard key={item.name} status={item} />)}
          </motion.div>
        )}
      </section>

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Visão geral</h2>
        {index.isLoading ? (
          <LoadingGrid count={6} />
        ) : index.isError ? (
          <ErrorState message={(index.error as Error).message} onRetry={() => index.refetch()} />
        ) : index.data ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            <MetricCard label="Usuários" value={formatNumber(index.data.users_total)} icon={Users} />
            <MetricCard label="Agents" value={formatNumber(index.data.agents_total)} icon={Bot} />
            <MetricCard label="Tools" value={formatNumber(index.data.tools_total)} icon={Wrench} />
            <MetricCard
              label="Contas Google"
              value={formatNumber(index.data.google_connected_accounts)}
              icon={ShieldCheck}
            />
            {/* Panel 5: WhatsApp connection status */}
            <MetricCard
              label="WhatsApp"
              value={index.data.whatsapp_connected ? "Conectado" : "Desconectado"}
              icon={MessageCircle}
              tone={index.data.whatsapp_connected ? "success" : "destructive"}
              hint={
                whatsapp.data
                  ? `${formatNumber(whatsapp.data.queue_depth)} na fila · ${formatNumber(whatsapp.data.messages_sent)} enviadas`
                  : undefined
              }
            />
            <MetricCard label="Uptime" value={formatUptime(index.data.uptime_seconds)} icon={Clock} />
          </div>
        ) : null}
        <p className="mt-2 text-xs text-muted-foreground">
          <Link href="/admin/whatsapp" className="text-primary hover:underline">
            Ver detalhes do WhatsApp →
          </Link>
        </p>
      </section>

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Gráficos em tempo real</h2>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Execuções/min</CardTitle>
            </CardHeader>
            <CardContent>
              <MetricChart data={executionsSeries} color="hsl(217 91% 60%)" />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Tokens/min</CardTitle>
            </CardHeader>
            <CardContent>
              <MetricChart data={tokensSeries} color="hsl(142 71% 45%)" />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Erros/min</CardTitle>
            </CardHeader>
            <CardContent>
              <MetricChart data={errorsSeries} color="hsl(0 72% 51%)" />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Latência média HTTP</CardTitle>
            </CardHeader>
            <CardContent>
              <MetricChart data={latencySeries} color="hsl(38 92% 50%)" unit="ms" />
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Operação</h2>

        {/* Panel 8: AI Suggested Actions — the Action Center */}
        <Card className="mb-4">
          <CardHeader>
            <CardTitle>Ações sugeridas</CardTitle>
          </CardHeader>
          <CardContent>
            {awaitingApproval.isLoading || failedJobs.isLoading || tasks.isLoading || readyGoals.isLoading ? (
              <LoadingRows count={3} />
            ) : (
              <SuggestedActionsPanel
                awaitingApproval={awaitingApproval.data ?? []}
                failedJobs={failedJobs.data ?? []}
                overdueTasks={overdueTasks}
                topReadyGoal={readyGoals.data?.[0] ?? null}
                onApproveGoal={(goalId) => approveGoal.mutate(goalId)}
                approvingGoalId={approvingGoalId}
                onRetryJob={(jobId) => retryJob.mutate(jobId)}
                retryingJobId={retryingJobId}
              />
            )}
          </CardContent>
        </Card>

        {/* Panel 1: CurrentContext */}
        <Card className="mb-4">
          <CardHeader>
            <CardTitle>Contexto atual (Context Observation Engine)</CardTitle>
          </CardHeader>
          <CardContent>
            {observation.isLoading ? (
              <LoadingRows count={2} />
            ) : observation.isError ? (
              <ErrorState message={(observation.error as Error).message} onRetry={() => observation.refetch()} />
            ) : observation.data ? (
              <CurrentContextPanel context={observation.data} />
            ) : null}
          </CardContent>
        </Card>

        <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Panel 2: Active Goals */}
          <Card>
            <CardHeader>
              <CardTitle>Metas ativas</CardTitle>
            </CardHeader>
            <CardContent>
              {readyGoals.isLoading ? (
                <LoadingRows count={3} />
              ) : readyGoals.isError ? (
                <ErrorState message={(readyGoals.error as Error).message} onRetry={() => readyGoals.refetch()} />
              ) : (
                <GoalsPanel goals={readyGoals.data ?? []} />
              )}
            </CardContent>
          </Card>

          {/* Panel 3: Today's Tasks */}
          <Card>
            <CardHeader>
              <CardTitle>Tarefas de hoje</CardTitle>
            </CardHeader>
            <CardContent>
              {tasks.isLoading ? (
                <LoadingRows count={3} />
              ) : tasks.isError ? (
                <ErrorState message={(tasks.error as Error).message} onRetry={() => tasks.refetch()} />
              ) : (
                <TasksPanel tasks={todaysTasks} />
              )}
            </CardContent>
          </Card>
        </div>

        <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Panel 4: Calendar */}
          <Card>
            <CardHeader>
              <CardTitle>Agenda</CardTitle>
            </CardHeader>
            <CardContent>
              {calendar.isLoading ? (
                <LoadingRows count={3} />
              ) : calendar.isError ? (
                <ErrorState message={(calendar.error as Error).message} onRetry={() => calendar.refetch()} />
              ) : (
                <CalendarPanel events={upcomingEvents} />
              )}
            </CardContent>
          </Card>

          {/* Panel 7: Pending Jobs */}
          <Card>
            <CardHeader>
              <CardTitle>Jobs pendentes</CardTitle>
            </CardHeader>
            <CardContent>
              {queuedJobs.isLoading || runningJobs.isLoading ? (
                <LoadingRows count={3} />
              ) : queuedJobs.isError || runningJobs.isError ? (
                <ErrorState
                  message={((queuedJobs.error ?? runningJobs.error) as Error).message}
                  onRetry={() => {
                    queuedJobs.refetch();
                    runningJobs.refetch();
                  }}
                />
              ) : (
                <PendingJobsPanel
                  jobs={pendingJobs}
                  onCancel={(jobId) => cancelJob.mutate(jobId)}
                  cancelingId={cancelingJobId}
                />
              )}
            </CardContent>
          </Card>
        </div>

        {/* Panel 10: Cognitive Pipeline activity */}
        <Card className="mb-4">
          <CardHeader>
            <CardTitle>Atividade do Cognitive Pipeline</CardTitle>
          </CardHeader>
          <CardContent>
            {pipelineLogs.isLoading ? (
              <LoadingRows count={3} />
            ) : pipelineLogs.isError ? (
              <ErrorState message={(pipelineLogs.error as Error).message} onRetry={() => pipelineLogs.refetch()} />
            ) : (
              <PipelineActivityPanel entries={pipelineLogs.data ?? []} />
            )}
          </CardContent>
        </Card>

        {/* Panel 6: Recent Events timeline */}
        <Card>
          <CardHeader>
            <CardTitle>Eventos recentes</CardTitle>
          </CardHeader>
          <CardContent>
            {recentLogs.isLoading ? (
              <LoadingRows count={5} />
            ) : recentLogs.isError ? (
              <ErrorState message={(recentLogs.error as Error).message} onRetry={() => recentLogs.refetch()} />
            ) : (
              <LogViewer
                logs={recentLogs.data ?? []}
                level={logLevel}
                onLevelChange={setLogLevel}
                search={logSearch}
                onSearchChange={setLogSearch}
              />
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
