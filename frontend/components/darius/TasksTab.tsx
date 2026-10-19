"use client";

import { useState } from "react";

import { EmptyState } from "@/components/admin/EmptyState";
import { LoadingRows } from "@/components/admin/LoadingGrid";
import { Button } from "@/components/admin/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/admin/ui/table";
import { ErrorLine, FilterSelect, Pager, TaskStatusBadge, truncate } from "@/components/darius/common";
import { useDariusTaskDetail, useDariusTasks } from "@/lib/darius-api";
import { DARIUS_TASK_STATUSES, type DariusTaskStatus } from "@/lib/darius-types";
import { formatDateTime } from "@/lib/format";

const PAGE_SIZE = 25;

function TaskDetail({ taskId, onClose }: { taskId: string; onClose: () => void }) {
  const { data, isLoading, isError, error } = useDariusTaskDetail(taskId);
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Tarefa {taskId}</CardTitle>
        <Button variant="outline" size="sm" onClick={onClose}>
          Fechar
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {isLoading ? (
          <LoadingRows count={3} />
        ) : isError ? (
          <ErrorLine error={error} />
        ) : data ? (
          <>
            <p className="whitespace-pre-wrap">{data.state.objective}</p>
            <p className="text-muted-foreground">
              Estado atual: {data.state.currentState ?? "indisponível"} · iterações: {data.state.iterations}
            </p>
            <div>
              <h3 className="mb-1 font-medium">Resultado</h3>
              {data.result.done ? (
                <p className="whitespace-pre-wrap rounded-md bg-muted/40 p-2">{data.result.result ?? "(vazio)"}</p>
              ) : (
                <p className="text-muted-foreground">
                  Ainda sem resultado final ({data.result.status}).
                  {data.result.error ? ` Erro: ${data.result.error}` : ""}
                </p>
              )}
            </div>
            <div>
              <h3 className="mb-1 font-medium">Trilha de execução</h3>
              {data.state.trace.length === 0 ? (
                <p className="text-muted-foreground">Sem passos registrados.</p>
              ) : (
                <ol className="flex flex-col gap-1">
                  {data.state.trace.map((step, index) => (
                    <li key={`${step.state}-${index}`} className="rounded-md border border-border px-2 py-1">
                      <span className="font-medium">{step.state}</span>
                      {step.timestamp ? <span className="text-muted-foreground"> · {formatDateTime(step.timestamp)}</span> : null}
                      {step.error ? <p className="text-destructive">{step.error}</p> : null}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function TasksTab() {
  const [status, setStatus] = useState<DariusTaskStatus | "">("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const { data, isLoading, isError, error } = useDariusTasks({
    status: status || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <FilterSelect
          label="Estado"
          value={status}
          onChange={(value) => {
            setStatus(value as DariusTaskStatus | "");
            setOffset(0);
          }}
          options={DARIUS_TASK_STATUSES}
        />
        {data ? <span className="text-sm text-muted-foreground">{data.total} tarefa(s)</span> : null}
      </div>

      {isLoading ? (
        <LoadingRows count={5} />
      ) : isError ? (
        <ErrorLine error={error} />
      ) : data && data.items.length === 0 ? (
        <EmptyState title="Nenhuma tarefa" description="O DARIUS não tem tarefas para este filtro." />
      ) : data ? (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Objetivo</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Criada em</TableHead>
                <TableHead className="text-right">Detalhe</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((task) => (
                <TableRow key={task.id}>
                  <TableCell title={task.objective}>{truncate(task.objective)}</TableCell>
                  <TableCell>
                    <TaskStatusBadge status={task.status} />
                  </TableCell>
                  <TableCell>{formatDateTime(task.createdAt)}</TableCell>
                  <TableCell className="text-right">
                    <Button variant="outline" size="sm" onClick={() => setSelected(task.id)}>
                      Ver {task.id.slice(0, 8)}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pager offset={offset} pageSize={PAGE_SIZE} nextOffset={data.next_offset} onChange={setOffset} />
        </>
      ) : null}

      {selected ? <TaskDetail taskId={selected} onClose={() => setSelected(null)} /> : null}
    </div>
  );
}
