import { Bot, Briefcase } from "lucide-react";

import { Badge } from "@/components/admin/ui/badge";
import { EmptyState } from "@/components/admin/EmptyState";
import { formatDateTime, formatDuration } from "@/lib/format";
import type { ExecutionEntry } from "@/lib/admin-types";

const STATUS_TONE: Record<string, "success" | "destructive" | "secondary" | "warning"> = {
  succeeded: "success",
  ok: "success",
  info: "secondary",
  failed: "destructive",
  error: "destructive",
  cancelled: "warning",
  running: "warning",
  queued: "secondary",
  warning: "warning",
};

export function ExecutionTimeline({ entries }: { entries: ExecutionEntry[] }) {
  if (entries.length === 0) {
    return (
      <EmptyState
        title="Nenhuma execução no período"
        description="Ajuste o período ou o filtro de agente, ou aguarde nova atividade."
      />
    );
  }

  return (
    <ol className="flex flex-col gap-3">
      {entries.map((entry) => {
        const tone = STATUS_TONE[entry.status.toLowerCase()] ?? "secondary";
        return (
          <li key={`${entry.kind}-${entry.id}`} className="flex gap-3 rounded-md border border-border bg-card p-3">
            <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted">
              {entry.kind === "job" ? (
                <Briefcase className="h-3.5 w-3.5 text-muted-foreground" />
              ) : (
                <Bot className="h-3.5 w-3.5 text-muted-foreground" />
              )}
            </div>
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{entry.name}</span>
                <Badge variant={tone}>{entry.status}</Badge>
                {entry.agent ? <Badge variant="outline">{entry.agent}</Badge> : null}
              </div>
              {entry.detail ? <p className="mt-1 text-xs text-muted-foreground">{entry.detail}</p> : null}
              <p className="mt-1 text-xs text-muted-foreground">
                {formatDateTime(entry.timestamp)}
                {entry.duration_seconds !== null ? ` · ${formatDuration(entry.duration_seconds)}` : ""}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
