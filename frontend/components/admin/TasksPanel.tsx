import { Badge } from "@/components/admin/ui/badge";
import { EmptyState } from "@/components/admin/EmptyState";
import { formatDateTime } from "@/lib/format";
import type { TaskPriority, TaskRead } from "@/lib/admin-types";

const PRIORITY_TONE: Record<TaskPriority, "secondary" | "warning" | "destructive"> = {
  low: "secondary",
  medium: "secondary",
  high: "destructive",
};

const PRIORITY_LABEL: Record<TaskPriority, string> = {
  low: "Baixa",
  medium: "Média",
  high: "Alta",
};

function isOverdue(dueDate: string | null): boolean {
  if (!dueDate) return false;
  return new Date(dueDate).getTime() < Date.now();
}

export function TasksPanel({ tasks }: { tasks: TaskRead[] }) {
  if (tasks.length === 0) {
    return <EmptyState title="Nenhuma tarefa para hoje" description="Sem tarefas pendentes vencendo hoje ou atrasadas." />;
  }

  return (
    <ul className="flex flex-col gap-2">
      {tasks.map((task) => {
        const overdue = isOverdue(task.due_date);
        return (
          <li key={task.id} className="flex items-start gap-3 rounded-md border border-border bg-card p-3">
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{task.title}</span>
                <Badge variant={PRIORITY_TONE[task.priority]}>{PRIORITY_LABEL[task.priority]}</Badge>
                {overdue ? <Badge variant="destructive">Atrasada</Badge> : null}
              </div>
              {task.due_date ? (
                <p className="mt-1 text-xs text-muted-foreground">Prazo: {formatDateTime(task.due_date)}</p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
