"use client";

import { Badge } from "@/components/admin/ui/badge";
import { Button } from "@/components/admin/ui/button";
import { explainError } from "@/lib/darius-api";

type BadgeVariant = NonNullable<React.ComponentProps<typeof Badge>["variant"]>;

const TASK_VARIANT: Record<string, BadgeVariant> = {
  COMPLETED: "success",
  FAILED: "destructive",
  CANCELLED: "secondary",
  PAUSED: "warning",
  RUNNING: "default",
  QUEUED: "default",
  PENDING: "default",
};

const LINK_VARIANT: Record<string, BadgeVariant> = {
  reply_queued: "success",
  failed: "destructive",
  cancelled: "secondary",
  expired: "secondary",
  submitted: "default",
  submitting: "warning",
  skipped: "outline",
};

const LINK_LABEL: Record<string, string> = {
  reply_queued: "resposta enviada à fila",
  failed: "falhou",
  cancelled: "cancelada",
  expired: "expirada",
  submitted: "aguardando DARIUS",
  submitting: "enviando ao DARIUS",
  skipped: "ignorada",
};

const TASK_LABEL: Record<string, string> = {
  PAUSED: "PAUSED (aguarda aprovação)",
};

/** What each class means for the operator: the decisive question is "may the action have happened?". */
export const FAILURE_CLASS_LABEL: Record<string, string> = {
  BEFORE_EFFECT_TRANSIENT: "falha transitória antes do efeito (nada foi feito; pode ser repetida)",
  BEFORE_EFFECT_PERMANENT: "falha permanente antes do efeito (nada foi feito; não será repetida)",
  EFFECT_UNKNOWN: "efeito desconhecido (a ação pode ter ocorrido; NÃO é repetida automaticamente)",
  EFFECT_CONFIRMED: "efeito confirmado (a ação ocorreu)",
  RETRIES_EXHAUSTED: "tentativas esgotadas (nada foi feito)",
};

export function TaskStatusBadge({ status }: { status: string }) {
  return <Badge variant={TASK_VARIANT[status] ?? "outline"}>{TASK_LABEL[status] ?? status}</Badge>;
}

export function LinkStatusBadge({ status }: { status: string }) {
  return <Badge variant={LINK_VARIANT[status] ?? "outline"}>{LINK_LABEL[status] ?? status}</Badge>;
}

/** Explicit "unavailable" marker: a number we could not read is never shown as 0 or as a guess. */
export function Unavailable({ reason }: { reason?: string }) {
  return (
    <span className="text-muted-foreground" title={reason}>
      indisponível
    </span>
  );
}

export function Banner({
  tone,
  children,
  role = "status",
}: {
  tone: "warning" | "destructive" | "info";
  children: React.ReactNode;
  role?: "status" | "alert";
}) {
  const classes = {
    warning: "border-warning/40 bg-warning/10 text-warning",
    destructive: "border-destructive/40 bg-destructive/10 text-destructive",
    info: "border-border bg-muted/40 text-foreground",
  }[tone];
  return (
    <div role={role} className={`rounded-md border px-3 py-2 text-sm ${classes}`}>
      {children}
    </div>
  );
}

export function ErrorLine({ error }: { error: unknown }) {
  const explained = explainError(error);
  return (
    <Banner tone="destructive" role="alert">
      <p className="font-medium">{explained.message}</p>
      {explained.hint ? <p className="mt-1 text-xs">{explained.hint}</p> : null}
      {explained.outcomeUnknown ? (
        <p className="mt-1 text-xs">
          O resultado é desconhecido: o DARIUS pode ter aplicado a ação. Confira o estado da tarefa antes de repetir.
        </p>
      ) : null}
    </Banner>
  );
}

export function Pager({
  offset,
  pageSize,
  nextOffset,
  onChange,
}: {
  offset: number;
  pageSize: number;
  nextOffset: number | null;
  onChange: (offset: number) => void;
}) {
  return (
    <div className="mt-3 flex items-center justify-end gap-2">
      <Button
        variant="outline"
        size="sm"
        disabled={offset <= 0}
        onClick={() => onChange(Math.max(0, offset - pageSize))}
      >
        Anterior
      </Button>
      <Button variant="outline" size="sm" disabled={nextOffset === null} onClick={() => onChange(nextOffset ?? offset)}>
        Próxima
      </Button>
    </div>
  );
}

export function FilterSelect({
  label,
  value,
  onChange,
  options,
  allLabel = "Todos",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  allLabel?: string;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-muted-foreground">
      {label}
      <select
        className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{allLabel}</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

export function truncate(text: string, max = 90): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}
