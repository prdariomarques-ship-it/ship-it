import { Badge } from "@/components/admin/ui/badge";
import { EmptyState } from "@/components/admin/EmptyState";
import { formatDateTime, formatDuration } from "@/lib/format";
import type { AdminLogEntry } from "@/lib/admin-types";

const PRIORITY_TONE: Record<string, "secondary" | "warning" | "destructive"> = {
  low: "secondary",
  normal: "secondary",
  high: "warning",
  urgent: "destructive",
};

export function PipelineActivityPanel({ entries }: { entries: AdminLogEntry[] }) {
  if (entries.length === 0) {
    return (
      <EmptyState
        title="Nenhuma execução do pipeline ainda"
        description="Aparece aqui assim que o Cognitive Pipeline processar uma mensagem."
      />
    );
  }

  return (
    <ul className="flex flex-col gap-2">
      {entries.map((entry) => {
        const payload = entry.payload as {
          intent?: string;
          priority?: string;
          agents?: string[];
          duration_ms?: number;
          needs_confirmation?: boolean;
        };
        return (
          <li key={entry.id} className="rounded-md border border-border bg-card p-3">
            <div className="flex flex-wrap items-center gap-2">
              {payload.intent ? <Badge variant="outline">{payload.intent}</Badge> : null}
              {payload.priority ? (
                <Badge variant={PRIORITY_TONE[payload.priority] ?? "secondary"}>{payload.priority}</Badge>
              ) : null}
              {payload.agents?.length ? (
                <span className="text-xs text-muted-foreground">{payload.agents.join(", ")}</span>
              ) : null}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {formatDateTime(entry.created_at)}
              {payload.duration_ms !== undefined ? ` · ${formatDuration(payload.duration_ms / 1000)}` : ""}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
