import { Bot } from "lucide-react";

import { ActionWorkflowControl } from "@/components/admin/ActionWorkflowControl";
import { Badge } from "@/components/admin/ui/badge";
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
}

export function BriefingRecommendationCard({ recommendation }: BriefingRecommendationCardProps) {
  const { insight, whyNow, consequenceIfIgnored } = recommendation;

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
      <div className="mt-2">
        <ActionWorkflowControl insight={insight} />
      </div>
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
