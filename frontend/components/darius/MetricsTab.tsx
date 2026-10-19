"use client";

import { LoadingRows } from "@/components/admin/LoadingGrid";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Banner, ErrorLine, Unavailable } from "@/components/darius/common";
import { useRuntimeMetrics } from "@/lib/darius-api";
import { DARIUS_TASK_STATUSES } from "@/lib/darius-types";
import { formatDateTime } from "@/lib/format";

type Dict = Record<string, unknown>;

const asDict = (value: unknown): Dict => (typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Dict) : {});
const asNumber = (value: unknown): number | null => (typeof value === "number" && Number.isFinite(value) ? value : null);

function Figure({ label, value, hint }: { label: string; value: number | string | null | undefined; hint?: string }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold" title={hint}>
        {value === null || value === undefined ? <Unavailable /> : value}
      </p>
    </div>
  );
}

const when = (epochMs: unknown): string | null => {
  const value = asNumber(epochMs);
  return value === null ? null : formatDateTime(new Date(value).toISOString());
};

/**
 * Runtime counters of the DARIUS engine, as reported by DARIUS itself. Nothing is derived client-side: a value the
 * engine did not report is "indisponível", never 0. Process counters reset when the DARIUS process restarts.
 */
export function MetricsTab() {
  const { data, isLoading, isError, error } = useRuntimeMetrics();

  if (isLoading) return <LoadingRows count={4} />;
  if (isError) return <ErrorLine error={error} />;
  if (!data) return null;

  const tasks = asDict(data.tasks);
  const byStatus = asDict(tasks.byStatus);
  const queue = asDict(data.queue);
  const engine = asDict(data.engine);
  const consumer = asDict(engine.consumer);
  const recovery = asDict(engine.recovery);
  const retry = asDict(engine.retry);
  const scheduler = asDict(data.scheduler);
  const tasksAvailable = tasks.available !== false;
  const schedulerEnabled = scheduler.enabled === true;

  return (
    <div className="flex flex-col gap-4">
      <Banner tone="info">
        <p className="font-medium">Gerado pelo DARIUS em {when(data.generatedAt) ?? "horário indisponível"}.</p>
        <p className="mt-1 text-xs">
          Contagens de tarefas vêm do armazenamento durável. Os contadores do processo (consumidor, recuperação, retry)
          zeram quando o DARIUS reinicia.
        </p>
      </Banner>

      <Card>
        <CardHeader>
          <CardTitle>Tarefas</CardTitle>
        </CardHeader>
        <CardContent>
          {!tasksAvailable ? (
            <Banner tone="warning">O armazenamento de tarefas não informou contagens: valores indisponíveis.</Banner>
          ) : (
            <div className="grid gap-3 sm:grid-cols-4">
              <Figure label="Total" value={asNumber(tasks.total)} />
              {DARIUS_TASK_STATUSES.map((status) => (
                <Figure key={status} label={status} value={asNumber(byStatus[status])} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Fila e retry automático</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-4">
            <Figure label="Na fila" value={asNumber(queue.queued)} />
            <Figure label="Em espera (backoff)" value={asNumber(queue.backingOff)} />
            <Figure label="Próxima tentativa" value={when(queue.nextRetryAt)} />
            <Figure label="Retries agendados" value={asNumber(retry.scheduledTotal)} />
          </div>
          {retry.enabled === true ? (
            <p className="text-sm text-muted-foreground">
              Retry ligado (máx. {asNumber(retry.maxRetries) ?? "indisponível"} tentativas; esgotadas:{" "}
              {asNumber(retry.exhaustedTotal) ?? "indisponível"}). Só falhas ANTES do efeito são repetidas.
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">Retry automático desligado: falhas não são repetidas.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Consumidor e recuperação</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-4">
          <Figure label="Consumidor" value={consumer.running === true ? "ativo" : consumer.running === false ? "parado" : null} />
          <Figure label="Em execução" value={asNumber(consumer.inflight)} />
          <Figure label="Tarefas iniciadas" value={asNumber(consumer.startedTotal)} />
          <Figure label="Último ciclo" value={when(consumer.lastPassAt)} />
          <Figure label="Recuperação" value={recovery.running === true ? "ativa" : recovery.running === false ? "parada" : null} />
          <Figure label="Varreduras" value={asNumber(recovery.sweeps)} />
          <Figure label="Reenfileiradas" value={asNumber(recovery.requeuedTotal)} />
          <Figure label="Última varredura" value={when(recovery.lastSweepAt)} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Agendador</CardTitle>
        </CardHeader>
        <CardContent>
          {schedulerEnabled ? (
            <div className="grid gap-3 sm:grid-cols-4">
              {Object.entries(scheduler)
                .filter(([key, value]) => key !== "enabled" && (asNumber(value) !== null || value === null))
                .map(([key, value]) => (
                  <Figure key={key} label={key} value={asNumber(value)} />
                ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Agendador desligado neste DARIUS (desligado por padrão).</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
