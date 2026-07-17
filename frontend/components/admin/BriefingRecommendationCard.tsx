import { Bot, RotateCcw, CheckCircle2 } from "lucide-react";

import { Badge } from "@/components/admin/ui/badge";
import { Button } from "@/components/admin/ui/button";
import type { BriefingRecommendation } from "@/lib/briefing";
import type { Severity } from "@/lib/operator";

const SEVERITY_TONE: Record<Severity, "destructive" | "warning" | "secondary"> = {
  urgent: "destructive",
  attention: "warning",
  info: "secondary",
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

interface BriefingRecommendationCardProps {
  recommendation: BriefingRecommendation;
  onApproveGoal?: (goalId: number) => void;
  approvingGoalId?: number | null;
  onRetryJob?: (jobId: number) => void;
  retryingJobId?: number | null;
}

export function BriefingRecommendationCard({
  recommendation,
  onApproveGoal,
  approvingGoalId,
  onRetryJob,
  retryingJobId,
}: BriefingRecommendationCardProps) {
  const { insight, whyNow, consequenceIfIgnored } = recommendation;
  const actionPending =
    insight.action?.kind === "approve_goal"
      ? approvingGoalId === insight.action.targetId
      : insight.action?.kind === "retry_job"
        ? retryingJobId === insight.action.targetId
        : false;

  return (
    <li className="rounded-md border border-border bg-card p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-sm font-medium">{insight.title}</span>
        <Badge variant={SEVERITY_TONE[insight.severity]}>{insight.severity}</Badge>
        <Badge variant={confidenceTone(insight.confidence)}>{insight.confidence}%</Badge>
        <Badge variant="outline">{estimatedTimeLabel(insight.estimatedMinutes)}</Badge>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Por quê: </span>
        {insight.reason}
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Por que agora: </span>
        {whyNow}
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Se ignorado: </span>
        {consequenceIfIgnored}
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Impacto esperado: </span>
        {insight.impact}
      </p>
      {insight.action && onApproveGoal && onRetryJob ? (
        <Button
          variant="outline"
          size="sm"
          className="mt-2"
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
    </li>
  );
}

export function AutomationCard({ recommendation }: { recommendation: BriefingRecommendation }) {
  return (
    <li className="flex items-start gap-2 rounded-md border border-border bg-card p-3">
      <Bot className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      <div>
        <p className="text-sm font-medium">{recommendation.insight.title}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{recommendation.insight.reason}</p>
      </div>
    </li>
  );
}
