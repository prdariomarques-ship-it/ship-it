"use client";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { SystemHealth } from "@/components/admin/SystemHealth";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { useAdminSystem } from "@/lib/admin-api";
import { formatUptime } from "@/lib/format";

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-border py-2 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

export default function AdminSystemPage() {
  const { data, isLoading, isError, error, refetch } = useAdminSystem();

  return (
    <div>
      <AdminPageHeader title="System" subtitle="Versão, build e uso de recursos do backend." />
      {isLoading ? (
        <LoadingGrid count={4} />
      ) : isError ? (
        <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
      ) : data ? (
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Build</CardTitle>
            </CardHeader>
            <CardContent>
              <InfoRow label="Aplicação" value={data.app_name} />
              <InfoRow label="Versão" value={data.version} />
              <InfoRow label="Ambiente" value={data.environment} />
              <InfoRow label="Commit" value={data.commit ?? "não disponível"} />
              <InfoRow label="Branch" value={data.branch ?? "não disponível"} />
              <InfoRow label="Tag" value={data.tag ?? "não disponível"} />
              <InfoRow label="Tempo online" value={formatUptime(data.uptime_seconds)} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Banco de dados</CardTitle>
            </CardHeader>
            <CardContent>
              <InfoRow
                label="Pool (tamanho)"
                value={data.db_pool_size !== null ? String(data.db_pool_size) : "não disponível"}
              />
              <InfoRow
                label="Pool (em uso)"
                value={data.db_pool_checked_out !== null ? String(data.db_pool_checked_out) : "não disponível"}
              />
            </CardContent>
          </Card>

          <div>
            <h2 className="mb-3 text-sm font-medium text-muted-foreground">Recursos</h2>
            <SystemHealth
              cpuPercent={data.cpu_percent}
              memoryPercent={data.memory_percent}
              memoryUsedMb={data.memory_used_mb}
              memoryTotalMb={data.memory_total_mb}
              diskPercent={data.disk_percent}
              diskUsedGb={data.disk_used_gb}
              diskTotalGb={data.disk_total_gb}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
