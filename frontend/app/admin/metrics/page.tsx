"use client";

import { useState } from "react";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { MetricChart } from "@/components/admin/charts/MetricChart";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Input } from "@/components/admin/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/admin/ui/table";
import { useAdminMetrics } from "@/lib/admin-api";
import { useRatePerMinute } from "@/hooks/use-rolling-series";
import { sumMetric } from "@/lib/metrics-helpers";

export default function AdminMetricsPage() {
  const [filter, setFilter] = useState("");
  const { data, isLoading, isError, error, refetch } = useAdminMetrics();

  const executionsTotal = sumMetric(data, "darioos_agent_runs_total");
  const errorsTotal = sumMetric(data, "darioos_agent_runs_total", { status: "error" });
  const tokensTotal =
    sumMetric(data, "darioos_agent_tokens_total", { kind: "prompt" }) +
    sumMetric(data, "darioos_agent_tokens_total", { kind: "completion" });
  const httpSum = sumMetric(data, "darioos_http_request_duration_seconds_sum");
  const httpCount = sumMetric(data, "darioos_http_request_duration_seconds_count");
  const avgLatencyMs = httpCount > 0 ? (httpSum / httpCount) * 1000 : null;

  const executionsSeries = useRatePerMinute(executionsTotal);
  const errorsSeries = useRatePerMinute(errorsTotal);
  const tokensSeries = useRatePerMinute(tokensTotal);
  const latencySeries = useRatePerMinute(avgLatencyMs);

  const rows = data
    ? Object.entries(data.metrics)
        .flatMap(([, samples]) => samples)
        .filter((sample) => sample.name.toLowerCase().includes(filter.toLowerCase()))
        .slice(0, 300)
    : [];

  return (
    <div>
      <AdminPageHeader
        title="Metrics"
        subtitle="Contadores acumulados do Prometheus (/metrics), convertidos em taxa por minuto no navegador — não é uma série histórica persistida."
      />

      {isLoading ? (
        <LoadingGrid count={4} />
      ) : isError ? (
        <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
      ) : (
        <>
          <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Execuções/min</CardTitle>
              </CardHeader>
              <CardContent>
                <MetricChart data={executionsSeries} color="hsl(217 91% 60%)" height={200} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Tokens/min</CardTitle>
              </CardHeader>
              <CardContent>
                <MetricChart data={tokensSeries} color="hsl(142 71% 45%)" height={200} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Erros/min</CardTitle>
              </CardHeader>
              <CardContent>
                <MetricChart data={errorsSeries} color="hsl(0 72% 51%)" height={200} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Latência média HTTP</CardTitle>
              </CardHeader>
              <CardContent>
                <MetricChart data={latencySeries} color="hsl(38 92% 50%)" unit="ms" height={200} />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Amostras brutas</CardTitle>
            </CardHeader>
            <CardContent>
              <Input
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                placeholder="Filtrar por nome da métrica…"
                className="mb-3 max-w-sm"
              />
              <div className="admin-scroll max-h-96 overflow-y-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Métrica</TableHead>
                      <TableHead>Labels</TableHead>
                      <TableHead className="text-right">Valor</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((sample, index) => (
                      <TableRow key={`${sample.name}-${index}`}>
                        <TableCell className="font-mono text-xs">{sample.name}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {Object.entries(sample.labels).map(([k, v]) => `${k}=${v}`).join(", ") || "—"}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs">{sample.value}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
