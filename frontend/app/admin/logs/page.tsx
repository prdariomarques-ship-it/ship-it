"use client";

import { useState } from "react";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { LogViewer } from "@/components/admin/LogViewer";
import { LoadingRows } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { Card, CardContent } from "@/components/admin/ui/card";
import { useAdminLogs } from "@/lib/admin-api";

export default function AdminLogsPage() {
  const [level, setLevel] = useState<string | undefined>(undefined);
  const [search, setSearch] = useState("");

  const { data, isLoading, isError, error, refetch } = useAdminLogs({ level, search, limit: 200 });

  return (
    <div>
      <AdminPageHeader title="Logs" subtitle="Visualizador de logs com filtro por nível e busca por texto." />
      <Card>
        <CardContent className="pt-4">
          {isLoading ? (
            <LoadingRows count={10} />
          ) : isError ? (
            <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
          ) : (
            <LogViewer
              logs={data ?? []}
              level={level}
              onLevelChange={setLevel}
              search={search}
              onSearchChange={setSearch}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
