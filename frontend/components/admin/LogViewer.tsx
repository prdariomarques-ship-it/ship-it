"use client";

import { useState } from "react";
import { Download } from "lucide-react";

import { Badge } from "@/components/admin/ui/badge";
import { Button } from "@/components/admin/ui/button";
import { Input } from "@/components/admin/ui/input";
import { EmptyState } from "@/components/admin/EmptyState";
import { formatDateTime } from "@/lib/format";
import type { AdminLogEntry } from "@/lib/admin-types";

const LEVELS = ["debug", "info", "warning", "error"] as const;

const LEVEL_TONE: Record<string, "secondary" | "success" | "warning" | "destructive"> = {
  debug: "secondary",
  info: "success",
  warning: "warning",
  error: "destructive",
};

interface LogViewerProps {
  logs: AdminLogEntry[];
  level: string | undefined;
  onLevelChange: (level: string | undefined) => void;
  search: string;
  onSearchChange: (value: string) => void;
}

function exportLogs(logs: AdminLogEntry[]) {
  const blob = new Blob([JSON.stringify(logs, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `dario-os-logs-${new Date().toISOString()}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

export function LogViewer({ logs, level, onLevelChange, search, onSearchChange }: LogViewerProps) {
  const [expanded, setExpanded] = useState<number | null>(null);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1">
          <Badge
            variant={level === undefined ? "default" : "outline"}
            className="cursor-pointer"
            onClick={() => onLevelChange(undefined)}
          >
            todos
          </Badge>
          {LEVELS.map((item) => (
            <Badge
              key={item}
              variant={level === item ? LEVEL_TONE[item] : "outline"}
              className="cursor-pointer uppercase"
              onClick={() => onLevelChange(item)}
            >
              {item}
            </Badge>
          ))}
        </div>
        <Input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Buscar na mensagem…"
          className="ml-auto max-w-xs"
        />
        <Button variant="outline" size="sm" onClick={() => exportLogs(logs)}>
          <Download className="h-3.5 w-3.5" />
          Exportar
        </Button>
      </div>

      {logs.length === 0 ? (
        <EmptyState title="Nenhum log encontrado" description="Ajuste os filtros ou a busca." />
      ) : (
        <div className="admin-scroll flex max-h-[65vh] flex-col gap-1 overflow-y-auto rounded-md border border-border bg-background p-2 font-mono text-xs">
          {logs.map((log) => (
            <div key={log.id} className="rounded-sm px-2 py-1.5 hover:bg-muted/50">
              <button
                type="button"
                onClick={() => setExpanded(expanded === log.id ? null : log.id)}
                className="flex w-full flex-wrap items-start gap-x-2 gap-y-1 text-left"
              >
                <span className="shrink-0 text-muted-foreground">{formatDateTime(log.created_at)}</span>
                <Badge variant={LEVEL_TONE[log.level] ?? "secondary"} className="shrink-0 uppercase">
                  {log.level}
                </Badge>
                <span className="shrink-0 text-muted-foreground">[{log.source}]</span>
                {/* Was `truncate` (nowrap + ellipsis) — on mobile, where the
                    row's other shrink-0 elements already fill the full
                    390px width by themselves, this cut long messages off
                    with no way to read the rest (clicking the row only
                    reveals the payload, not the message itself). basis-full
                    on the parent's flex-wrap drops the message to its own
                    line when there's no room left in the metadata row,
                    instead of squeezing it into a 0-width column that still
                    wrapped every character onto its own (invisible) line. */}
                <span className="min-w-0 basis-full whitespace-normal break-words text-foreground sm:basis-auto sm:flex-1">
                  {log.message}
                </span>
              </button>
              {expanded === log.id && Object.keys(log.payload).length > 0 ? (
                <pre className="admin-scroll mt-1.5 max-h-40 overflow-auto rounded-sm bg-muted/40 p-2">
                  {JSON.stringify(log.payload, null, 2)}
                </pre>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
