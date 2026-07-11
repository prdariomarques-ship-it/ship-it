"use client";

import { useState } from "react";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { ExecutionTimeline } from "@/components/admin/ExecutionTimeline";
import { LoadingRows } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { Card, CardContent } from "@/components/admin/ui/card";
import { Input } from "@/components/admin/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/admin/ui/select";
import { useAdminExecutions } from "@/lib/admin-api";
import type { ExecutionsPeriod } from "@/lib/admin-types";

const PERIODS: { value: ExecutionsPeriod; label: string }[] = [
  { value: "today", label: "Hoje" },
  { value: "24h", label: "24 horas" },
  { value: "7d", label: "7 dias" },
  { value: "30d", label: "30 dias" },
];

export default function AdminExecutionsPage() {
  const [period, setPeriod] = useState<ExecutionsPeriod>("24h");
  const [agent, setAgent] = useState("");

  const { data, isLoading, isError, error, refetch } = useAdminExecutions({
    period,
    agent: agent || undefined,
  });

  return (
    <div>
      <AdminPageHeader
        title="Executions"
        subtitle="Timeline construída a partir de jobs em background e logs de agente — não há tabela dedicada de auditoria de execuções (ver docs/DASHBOARD.md)."
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Select value={period} onValueChange={(value) => setPeriod(value as ExecutionsPeriod)}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PERIODS.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          value={agent}
          onChange={(event) => setAgent(event.target.value)}
          placeholder="Filtrar por agente…"
          className="w-56"
        />
      </div>

      <Card>
        <CardContent className="pt-4">
          {isLoading ? (
            <LoadingRows count={6} />
          ) : isError ? (
            <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
          ) : (
            <ExecutionTimeline entries={data ?? []} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
