import { Badge } from "@/components/admin/ui/badge";
import { EmptyState } from "@/components/admin/EmptyState";
import { formatDateTime } from "@/lib/format";
import type { GoalPriority, GoalRead } from "@/lib/admin-types";

const PRIORITY_TONE: Record<GoalPriority, "secondary" | "success" | "warning" | "destructive"> = {
  low: "secondary",
  medium: "success",
  high: "warning",
  urgent: "destructive",
};

const PRIORITY_LABEL: Record<GoalPriority, string> = {
  low: "Baixa",
  medium: "Média",
  high: "Alta",
  urgent: "Urgente",
};

export function GoalsPanel({ goals }: { goals: GoalRead[] }) {
  if (goals.length === 0) {
    return (
      <EmptyState
        title="Nenhuma meta pronta"
        description="Sem metas pendentes com dependências resolvidas no momento."
      />
    );
  }

  return (
    <ul className="flex flex-col gap-2">
      {goals.map((goal) => (
        <li key={goal.id} className="rounded-md border border-border bg-card p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{goal.title}</span>
            <Badge variant={PRIORITY_TONE[goal.priority]}>{PRIORITY_LABEL[goal.priority]}</Badge>
          </div>
          <div className="mt-1.5 flex items-center gap-2">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${goal.progress_percent}%` }}
              />
            </div>
            <span className="shrink-0 text-xs text-muted-foreground">{goal.progress_percent}%</span>
          </div>
          {goal.deadline ? (
            <p className="mt-1 text-xs text-muted-foreground">Prazo: {formatDateTime(goal.deadline)}</p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
