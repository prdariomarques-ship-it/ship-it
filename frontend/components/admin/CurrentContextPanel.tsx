import { AlertTriangle } from "lucide-react";

import { Badge } from "@/components/admin/ui/badge";
import { EmptyState } from "@/components/admin/EmptyState";
import { formatRelativeTime } from "@/lib/format";
import type { ContextItem, CurrentContext } from "@/lib/admin-types";

const SECTION_LABELS: Record<
  Exclude<keyof CurrentContext, "user_id" | "generated_at" | "trigger" | "degraded_sources">,
  string
> = {
  goals: "Metas",
  tasks: "Tarefas",
  calendar: "Agenda",
  recent_events: "Eventos",
  conversations: "Conversas",
  pending_work: "Trabalho pendente",
  memory: "Memória",
};

const SECTION_ORDER = Object.keys(SECTION_LABELS) as (keyof typeof SECTION_LABELS)[];

function Section({ label, items }: { label: string; items: ContextItem[] }) {
  return (
    <div className="rounded-md border border-border bg-background p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
        <Badge variant="outline">{items.length}</Badge>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-muted-foreground">Nada aqui agora.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {items.slice(0, 3).map((item, index) => (
            <li key={index} className="truncate text-xs text-foreground" title={item.content}>
              {item.content}
            </li>
          ))}
          {items.length > 3 ? (
            <li className="text-xs text-muted-foreground">+{items.length - 3} mais</li>
          ) : null}
        </ul>
      )}
    </div>
  );
}

export function CurrentContextPanel({ context }: { context: CurrentContext }) {
  const totalItems = SECTION_ORDER.reduce((sum, key) => sum + context[key].length, 0);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>Gerado {formatRelativeTime(context.generated_at)}</span>
        <Badge variant="outline">{context.trigger}</Badge>
        <span>·</span>
        <span>{totalItems} itens observados</span>
      </div>

      {context.degraded_sources.length > 0 ? (
        <div className="flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span>
            Fontes indisponíveis nesta observação: {context.degraded_sources.join(", ")}
          </span>
        </div>
      ) : null}

      {totalItems === 0 ? (
        <EmptyState
          title="Nada observado ainda"
          description="O sistema ainda não tem metas, tarefas, eventos ou trabalho pendente para relatar."
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {SECTION_ORDER.map((key) => (
            <Section key={key} label={SECTION_LABELS[key]} items={context[key]} />
          ))}
        </div>
      )}
    </div>
  );
}
