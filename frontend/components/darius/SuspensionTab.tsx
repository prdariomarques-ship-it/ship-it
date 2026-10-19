"use client";

import { useState } from "react";

import { LoadingRows } from "@/components/admin/LoadingGrid";
import { Badge } from "@/components/admin/ui/badge";
import { Button } from "@/components/admin/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Input } from "@/components/admin/ui/input";
import { Banner, ErrorLine } from "@/components/darius/common";
import { useSetSuspension, useSuspension } from "@/lib/darius-api";
import type { SuspensionState } from "@/lib/darius-types";
import { formatDateTime } from "@/lib/format";

const MIN_REASON = 3;

interface Target {
  /** undefined = the global switch */
  instance?: string;
  suspended: boolean;
}

function detailFor(state: SuspensionState, scope: string) {
  return state.details.find((item) => item.scope === scope);
}

function ScopeRow({
  title,
  suspended,
  reason,
  since,
  onAct,
  busy,
}: {
  title: string;
  suspended: boolean;
  reason?: string;
  since?: string | null;
  onAct: () => void;
  busy: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border py-3 last:border-0">
      <div>
        <p className="text-sm font-medium">{title}</p>
        {suspended ? (
          <p className="text-xs text-muted-foreground">
            {reason ?? "motivo não informado"}
            {since ? ` · desde ${formatDateTime(since)}` : ""}
          </p>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        <Badge variant={suspended ? "destructive" : "success"}>{suspended ? "suspensa" : "ativa"}</Badge>
        <Button
          size="sm"
          variant={suspended ? "default" : "outline"}
          onClick={onAct}
          disabled={busy}
          aria-label={`${suspended ? "Retomar" : "Suspender"} ${title}`}
        >
          {suspended ? "Retomar" : "Suspender"}
        </Button>
      </div>
    </div>
  );
}

/**
 * Global / per-instance automation suspension. A suspension withholds queued and new automatic replies
 * (owner alerts and human sends from this panel are not affected). Every change needs a reason (it is
 * audited) and an explicit confirmation, and resuming never releases withheld jobs in a burst.
 */
export function SuspensionTab() {
  const { data, isLoading, isError, error } = useSuspension();
  const mutation = useSetSuspension();
  const [target, setTarget] = useState<Target | null>(null);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const trimmed = reason.trim();
  const valid = trimmed.length >= MIN_REASON;

  const confirm = () => {
    if (!target || !valid) return;
    setNotice(null);
    mutation.mutate(
      { instance: target.instance, suspended: target.suspended, reason: trimmed },
      {
        onSuccess: (state) => {
          const where = target.instance ? `instância ${target.instance}` : "global";
          setNotice(
            state.changed === false
              ? `Sem mudança: a automação (${where}) já estava ${target.suspended ? "suspensa" : "ativa"}.`
              : `Automação (${where}) ${target.suspended ? "suspensa" : "retomada"}.`
          );
          setTarget(null);
          setReason("");
        },
      }
    );
  };

  const begin = (next: Target) => {
    mutation.reset();
    setNotice(null);
    setReason("");
    setTarget(next);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Suspensão da automação</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {notice ? <Banner tone="info">{notice}</Banner> : null}
        {isLoading ? (
          <LoadingRows count={3} />
        ) : isError ? (
          <ErrorLine error={error} />
        ) : data ? (
          <>
            {data.global_forced_by_environment ? (
              <Banner tone="destructive" role="alert">
                A automação está suspensa pela variável de ambiente do backend (AUTOMATION_SUSPENDED). O painel não
                consegue retomá-la: é preciso mudar a configuração e reiniciar.
              </Banner>
            ) : null}
            <ScopeRow
              title="Global (todas as instâncias)"
              suspended={data.global_suspended}
              reason={detailFor(data, "global")?.reason}
              since={detailFor(data, "global")?.since}
              busy={mutation.isPending}
              onAct={() => begin({ suspended: !data.global_suspended })}
            />
            {data.configured_instances.map((name) => {
              const suspended = data.suspended_instances.includes(name);
              const detail = detailFor(data, `instance:${name}`);
              return (
                <ScopeRow
                  key={name}
                  title={`Instância ${name}`}
                  suspended={suspended}
                  reason={detail?.reason}
                  since={detail?.since}
                  busy={mutation.isPending}
                  onAct={() => begin({ instance: name, suspended: !suspended })}
                />
              );
            })}

            {target ? (
              <div className="flex flex-col gap-2 rounded-md border border-border p-3" role="group" aria-label="Confirmar suspensão">
                <p className="text-sm font-medium">
                  {target.suspended ? "Suspender" : "Retomar"} a automação{" "}
                  {target.instance ? `da instância ${target.instance}` : "global"}?
                </p>
                <Input
                  aria-label="Motivo"
                  placeholder={`Motivo obrigatório (mínimo ${MIN_REASON} caracteres)`}
                  maxLength={500}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
                {mutation.isError ? <ErrorLine error={mutation.error} /> : null}
                <div className="flex gap-2">
                  <Button size="sm" onClick={confirm} disabled={!valid || mutation.isPending}>
                    {mutation.isPending ? "Aplicando…" : "Confirmar"}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setTarget(null)} disabled={mutation.isPending}>
                    Voltar
                  </Button>
                </div>
              </div>
            ) : null}
            <p className="text-xs text-muted-foreground">
              A suspensão retém respostas automáticas já enfileiradas e novas. Alertas ao dono e envios humanos feitos
              neste painel continuam saindo. Ao retomar, o que foi retido não é liberado em rajada.
            </p>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
