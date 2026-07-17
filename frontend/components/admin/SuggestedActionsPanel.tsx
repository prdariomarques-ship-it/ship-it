"use client";

import { AlertOctagon, CheckCircle2, ListTodo, RotateCcw, Target } from "lucide-react";

import { Badge } from "@/components/admin/ui/badge";
import { Button } from "@/components/admin/ui/button";
import { EmptyState } from "@/components/admin/EmptyState";
import { formatDateTime } from "@/lib/format";
import type { GoalRead, JobRead, TaskRead } from "@/lib/admin-types";

interface SuggestedAction {
  key: string;
  icon: React.ElementType;
  tone: "warning" | "destructive" | "secondary";
  title: string;
  detail: string;
  actionLabel?: string;
  onAction?: () => void;
  actionPending?: boolean;
}

interface SuggestedActionsPanelProps {
  awaitingApproval: GoalRead[];
  failedJobs: JobRead[];
  overdueTasks: TaskRead[];
  topReadyGoal: GoalRead | null;
  onApproveGoal: (goalId: number) => void;
  approvingGoalId: number | null;
  onRetryJob: (jobId: number) => void;
  retryingJobId: number | null;
}

export function SuggestedActionsPanel({
  awaitingApproval,
  failedJobs,
  overdueTasks,
  topReadyGoal,
  onApproveGoal,
  approvingGoalId,
  onRetryJob,
  retryingJobId,
}: SuggestedActionsPanelProps) {
  const actions: SuggestedAction[] = [
    ...awaitingApproval.map((goal) => ({
      key: `approve-${goal.id}`,
      icon: CheckCircle2,
      tone: "warning" as const,
      title: `Aprovar meta: ${goal.title}`,
      detail: "Criada com requires_approval — precisa da sua aprovação para começar.",
      actionLabel: approvingGoalId === goal.id ? "Aprovando…" : "Aprovar",
      onAction: () => onApproveGoal(goal.id),
      actionPending: approvingGoalId === goal.id,
    })),
    ...failedJobs.map((job) => ({
      key: `retry-${job.id}`,
      icon: AlertOctagon,
      tone: "destructive" as const,
      title: `Job falhou: ${job.name}`,
      detail: job.last_error || `${job.attempts}/${job.max_attempts} tentativas esgotadas.`,
      actionLabel: retryingJobId === job.id ? "Reenviando…" : "Tentar novamente",
      onAction: () => onRetryJob(job.id),
      actionPending: retryingJobId === job.id,
    })),
    ...overdueTasks.slice(0, 5).map((task) => ({
      key: `task-${task.id}`,
      icon: ListTodo,
      tone: "warning" as const,
      title: `Tarefa atrasada: ${task.title}`,
      detail: task.due_date ? `Venceu em ${formatDateTime(task.due_date)}` : "Sem prazo definido.",
    })),
    ...(topReadyGoal
      ? [
          {
            key: `next-goal-${topReadyGoal.id}`,
            icon: Target,
            tone: "secondary" as const,
            title: `Próxima meta sugerida: ${topReadyGoal.title}`,
            detail: `Prioridade ${topReadyGoal.priority} · ${topReadyGoal.progress_percent}% concluída — pronta para avançar.`,
          },
        ]
      : []),
  ];

  if (actions.length === 0) {
    return (
      <EmptyState
        title="Tudo em dia"
        description="Nenhuma meta aguardando aprovação, job falhado ou tarefa atrasada agora."
        icon={CheckCircle2}
      />
    );
  }

  const TONE_BADGE: Record<SuggestedAction["tone"], "warning" | "destructive" | "secondary"> = {
    warning: "warning",
    destructive: "destructive",
    secondary: "secondary",
  };

  return (
    <ul className="flex flex-col gap-2">
      {actions.map((action) => {
        const Icon = action.icon;
        return (
          <li
            key={action.key}
            className="flex items-start gap-3 rounded-md border border-border bg-card p-3"
          >
            <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted">
              <Icon className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{action.title}</span>
                <Badge variant={TONE_BADGE[action.tone]}>
                  {action.tone === "destructive" ? "urgente" : action.tone === "warning" ? "atenção" : "info"}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{action.detail}</p>
            </div>
            {action.onAction ? (
              <Button
                variant="outline"
                size="sm"
                disabled={action.actionPending}
                onClick={action.onAction}
              >
                {action.tone === "destructive" ? (
                  <RotateCcw className="h-3.5 w-3.5" />
                ) : (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                )}
                {action.actionLabel}
              </Button>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
