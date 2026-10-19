"use client";

import { useState } from "react";

import { EmptyState } from "@/components/admin/EmptyState";
import { LoadingRows } from "@/components/admin/LoadingGrid";
import { Button } from "@/components/admin/ui/button";
import { Card, CardContent } from "@/components/admin/ui/card";
import { Input } from "@/components/admin/ui/input";
import { Banner, ErrorLine, Pager } from "@/components/darius/common";
import { useDariusDecision, useDariusTasks } from "@/lib/darius-api";
import type { DariusDecision, DariusTaskSummary } from "@/lib/darius-types";
import { formatDateTime } from "@/lib/format";

const PAGE_SIZE = 10;

const LABEL: Record<DariusDecision, string> = { approve: "Aprovar", reject: "Rejeitar", cancel: "Cancelar tarefa" };
const DONE: Record<DariusDecision, string> = {
  approve: "aprovada",
  reject: "rejeitada",
  cancel: "cancelada",
};

interface Pending {
  task: DariusTaskSummary;
  decision: DariusDecision;
}

/**
 * Tasks waiting for a human (DARIUS status PAUSED). The panel only relays the decision: DARIUS re-validates
 * it where the action executes, and the backend audits it with the admin user. Each decision needs an
 * explicit confirmation, and a task that already moved on (409) is shown as such instead of retried.
 */
export function ApprovalsTab() {
  const [offset, setOffset] = useState(0);
  const [pending, setPending] = useState<Pending | null>(null);
  const [reason, setReason] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const { data, isLoading, isError, error } = useDariusTasks({ status: "PAUSED", limit: PAGE_SIZE, offset });
  const decision = useDariusDecision();

  const confirm = () => {
    if (!pending) return;
    const { task, decision: kind } = pending;
    setDone(null);
    decision.mutate(
      { taskId: task.id, decision: kind, reason: kind === "reject" ? reason : undefined },
      {
        onSuccess: () => {
          setDone(`Tarefa ${task.id} ${DONE[kind]}.`);
          setPending(null);
          setReason("");
        },
      }
    );
  };

  return (
    <div className="flex flex-col gap-4">
      {done ? <Banner tone="info">{done}</Banner> : null}

      {isLoading ? (
        <LoadingRows count={3} />
      ) : isError ? (
        <ErrorLine error={error} />
      ) : data && data.items.length === 0 ? (
        <EmptyState title="Nada aguardando aprovação" description="Nenhuma tarefa está em PAUSED no DARIUS." />
      ) : data ? (
        <>
          <p className="text-sm text-muted-foreground">{data.total} tarefa(s) aguardando decisão humana</p>
          <ul className="flex flex-col gap-3">
            {data.items.map((task) => (
              <li key={task.id}>
                <Card>
                  <CardContent className="flex flex-col gap-3 pt-4">
                    <div>
                      <p className="whitespace-pre-wrap text-sm">{task.objective}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {task.id} · criada em {formatDateTime(task.createdAt)}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {(["approve", "reject", "cancel"] as DariusDecision[]).map((kind) => (
                        <Button
                          key={kind}
                          size="sm"
                          variant={kind === "approve" ? "default" : "outline"}
                          disabled={decision.isPending}
                          onClick={() => {
                            decision.reset();
                            setPending({ task, decision: kind });
                          }}
                          aria-label={`${LABEL[kind]} ${task.id}`}
                        >
                          {LABEL[kind]}
                        </Button>
                      ))}
                    </div>

                    {pending?.task.id === task.id ? (
                      <div className="flex flex-col gap-2 rounded-md border border-border p-3" role="group" aria-label="Confirmar decisão">
                        <p className="text-sm font-medium">
                          Confirmar: {LABEL[pending.decision].toLowerCase()} a tarefa {task.id}?
                        </p>
                        {pending.decision === "reject" ? (
                          <Input
                            aria-label="Motivo da rejeição"
                            placeholder="Motivo (opcional, até 500 caracteres)"
                            maxLength={500}
                            value={reason}
                            onChange={(event) => setReason(event.target.value)}
                          />
                        ) : null}
                        {decision.isError ? <ErrorLine error={decision.error} /> : null}
                        <div className="flex gap-2">
                          <Button size="sm" onClick={confirm} disabled={decision.isPending}>
                            {decision.isPending ? "Enviando…" : "Confirmar"}
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => setPending(null)} disabled={decision.isPending}>
                            Voltar
                          </Button>
                        </div>
                      </div>
                    ) : null}
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
          <Pager offset={offset} pageSize={PAGE_SIZE} nextOffset={data.next_offset} onChange={setOffset} />
        </>
      ) : null}
    </div>
  );
}
