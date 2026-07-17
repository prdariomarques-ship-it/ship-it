"use client";

import {
  Activity,
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Clock,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  Target,
  Zap,
} from "lucide-react";

import { Badge } from "@/components/admin/ui/badge";
import { Button } from "@/components/admin/ui/button";
import { EmptyState } from "@/components/admin/EmptyState";
import { confidenceSummary } from "@/lib/operator";
import type { Confidence, OperatorCategory, OperatorInsight, Severity } from "@/lib/operator";

const CATEGORY_ORDER: OperatorCategory[] = [
  "risk",
  "highest_priority",
  "follow_up",
  "missed_task",
  "calendar_conflict",
  "opportunity",
  "automatable",
  "recent_change",
];

const CATEGORY_LABEL: Record<OperatorCategory, string> = {
  highest_priority: "Mais importante hoje",
  follow_up: "Follow-ups pendentes",
  missed_task: "Tarefas perdidas",
  calendar_conflict: "Conflitos de agenda",
  risk: "Riscos",
  opportunity: "Oportunidades",
  automatable: "O que já está automatizado",
  recent_change: "Mudanças recentes observadas",
};

const CATEGORY_ICON: Record<OperatorCategory, React.ElementType> = {
  highest_priority: Target,
  follow_up: Clock,
  missed_task: AlertTriangle,
  calendar_conflict: CalendarClock,
  risk: ShieldAlert,
  opportunity: Sparkles,
  automatable: Zap,
  recent_change: Activity,
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

const CONFIDENCE_TONE: Record<Confidence, "success" | "secondary" | "outline"> = {
  high: "success",
  medium: "secondary",
  low: "outline",
};

const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: "alta confiança",
  medium: "confiança média",
  low: "baixa confiança",
};

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
  if (insights.length === 0) {
    return (
      <EmptyState
        title="Tudo em dia"
        description="Nenhum risco, follow-up pendente ou tarefa perdida agora — nada que precise da sua atenção neste momento."
        icon={CheckCircle2}
      />
    );
  }

  const grouped = CATEGORY_ORDER.map((category) => ({
    category,
    items: insights.filter((insight) => insight.category === category),
  })).filter((group) => group.items.length > 0);

  return (
    <div className="flex flex-col gap-5">
      <p className="text-xs text-muted-foreground">{confidenceSummary(insights)}</p>

      {grouped.map(({ category, items }) => {
        const Icon = CATEGORY_ICON[category];
        return (
          <div key={category}>
            <h3 className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <Icon className="h-3.5 w-3.5" />
              {CATEGORY_LABEL[category]}
            </h3>
            <ul className="flex flex-col gap-2">
              {items.map((insight) => (
                <li
                  key={insight.id}
                  className="flex items-start gap-3 rounded-md border border-border bg-card p-3"
                >
                  <div className="flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">{insight.title}</span>
                      <Badge variant={SEVERITY_TONE[insight.severity]}>{SEVERITY_LABEL[insight.severity]}</Badge>
                      <Badge variant={CONFIDENCE_TONE[insight.confidence]}>{CONFIDENCE_LABEL[insight.confidence]}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">Por quê: </span>
                      {insight.reason}
                    </p>
                  </div>
                  {insight.action ? (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={
                        insight.action.kind === "approve_goal"
                          ? approvingGoalId === insight.action.targetId
                          : retryingJobId === insight.action.targetId
                      }
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
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
