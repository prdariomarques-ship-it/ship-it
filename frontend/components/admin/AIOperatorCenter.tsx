"use client";

import { Check, CheckCircle2, Clock3, RotateCcw, X } from "lucide-react";

import { Badge } from "@/components/admin/ui/badge";
import { Button } from "@/components/admin/ui/button";
import { EmptyState } from "@/components/admin/EmptyState";
import { useOperatorInsightState } from "@/hooks/use-operator-state";
import { topInsight } from "@/lib/operator";
import type { OperatorBucket, OperatorInsight, Severity } from "@/lib/operator";

const BUCKET_ORDER: OperatorBucket[] = ["urgent", "today", "opportunity", "automation"];

const BUCKET_LABEL: Record<OperatorBucket, string> = {
  urgent: "🔥 Requer atenção imediata",
  today: "⚠️ Precisa de atenção hoje",
  opportunity: "💡 Oportunidades",
  automation: "🤖 Automações disponíveis",
};

const SEVERITY_TONE: Record<Severity, "destructive" | "warning" | "secondary"> = {
  urgent: "destructive",
  attention: "warning",
  info: "secondary",
};

const SEVERITY_LABEL: Record<Severity, string> = {
  urgent: "urgente",
  attention: "atenção",
  info: "info",
};

function confidenceTone(confidence: number): "success" | "secondary" | "outline" {
  if (confidence >= 90) return "success";
  if (confidence >= 50) return "secondary";
  return "outline";
}

function estimatedTimeLabel(minutes: number | null): string {
  if (minutes === null) return "tempo variável";
  if (minutes < 60) return `~${minutes}min`;
  return `~${Math.round(minutes / 60)}h`;
}

interface InsightRowProps {
  insight: OperatorInsight;
  onApproveGoal: (goalId: number) => void;
  approvingGoalId: number | null;
  onRetryJob: (jobId: number) => void;
  retryingJobId: number | null;
  onDismiss: (id: string) => void;
  onSnooze: (id: string) => void;
  onComplete: (id: string) => void;
  highlight?: boolean;
}

function InsightRow({
  insight,
  onApproveGoal,
  approvingGoalId,
  onRetryJob,
  retryingJobId,
  onDismiss,
  onSnooze,
  onComplete,
  highlight = false,
}: InsightRowProps) {
  const actionPending =
    insight.action?.kind === "approve_goal"
      ? approvingGoalId === insight.action.targetId
      : insight.action?.kind === "retry_job"
        ? retryingJobId === insight.action.targetId
        : false;

  return (
    <li
      className={`flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-start sm:justify-between ${
        highlight ? "border-primary/50 bg-primary/5" : "border-border bg-card"
      }`}
    >
      <div className="flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{insight.title}</span>
          <Badge variant={SEVERITY_TONE[insight.severity]}>{SEVERITY_LABEL[insight.severity]}</Badge>
          <Badge variant={confidenceTone(insight.confidence)}>{insight.confidence}% confiança</Badge>
          <Badge variant="outline">{estimatedTimeLabel(insight.estimatedMinutes)}</Badge>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Por quê: </span>
          {insight.reason}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Impacto esperado: </span>
          {insight.impact}
        </p>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-1.5">
        {insight.action ? (
          <Button
            variant="outline"
            size="sm"
            disabled={actionPending}
            onClick={() =>
              insight.action?.kind === "approve_goal"
                ? onApproveGoal(insight.action.targetId)
                : onRetryJob(insight.action!.targetId)
            }
          >
            {insight.action.kind === "retry_job" ? (
              <RotateCcw className="h-3.5 w-3.5" />
            ) : (
              <CheckCircle2 className="h-3.5 w-3.5" />
            )}
            {insight.action.label}
          </Button>
        ) : null}
        <Button variant="ghost" size="sm" title="Marcar como concluída" onClick={() => onComplete(insight.id)}>
          <Check className="h-3.5 w-3.5" />
        </Button>
        <Button variant="ghost" size="sm" title="Adiar por 4h" onClick={() => onSnooze(insight.id)}>
          <Clock3 className="h-3.5 w-3.5" />
        </Button>
        <Button variant="ghost" size="sm" title="Dispensar" onClick={() => onDismiss(insight.id)}>
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
    </li>
  );
}

interface AIOperatorCenterProps {
  insights: OperatorInsight[];
  onApproveGoal: (goalId: number) => void;
  approvingGoalId: number | null;
  onRetryJob: (jobId: number) => void;
  retryingJobId: number | null;
}

export function AIOperatorCenter({
  insights,
  onApproveGoal,
  approvingGoalId,
  onRetryJob,
  retryingJobId,
}: AIOperatorCenterProps) {
  const { isHidden, dismiss, complete, snooze } = useOperatorInsightState();

  // recent_change is history (Timeline's domain, see MEMORY_TIMELINE.md),
  // never an actionable to-do — kept out of the command-center view.
  const visible = insights.filter(
    (insight) => insight.category !== "recent_change" && !isHidden(insight.id)
  );

  if (visible.length === 0) {
    return (
      <EmptyState
        title="Tudo em dia"
        description="Nenhum risco, follow-up pendente ou tarefa perdida agora — nada que precise da sua atenção neste momento."
        icon={CheckCircle2}
      />
    );
  }

  const doNow = topInsight(visible);
  const grouped = BUCKET_ORDER.map((bucket) => ({
    bucket,
    items: visible.filter((insight) => insight.bucket === bucket && insight.id !== doNow?.id),
  })).filter((group) => group.items.length > 0);

  const rowProps = {
    onApproveGoal,
    approvingGoalId,
    onRetryJob,
    retryingJobId,
    onDismiss: dismiss,
    onSnooze: snooze,
    onComplete: complete,
  };

  return (
    <div className="flex flex-col gap-5">
      {doNow ? (
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Faça isso agora
          </h3>
          <ul>
            <InsightRow insight={doNow} highlight {...rowProps} />
          </ul>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Nada urgente agora — veja as oportunidades e automações abaixo.
        </p>
      )}

      {grouped.map(({ bucket, items }) => (
        <div key={bucket}>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {BUCKET_LABEL[bucket]}
          </h3>
          <ul className="flex flex-col gap-2">
            {items.map((insight) => (
              <InsightRow key={insight.id} insight={insight} {...rowProps} />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
