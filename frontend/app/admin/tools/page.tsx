"use client";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { ToolTable } from "@/components/admin/ToolTable";
import { LoadingRows } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { Card, CardContent } from "@/components/admin/ui/card";
import { useAdminTools } from "@/lib/admin-api";

export default function AdminToolsPage() {
  const { data, isLoading, isError, error, refetch } = useAdminTools();

  return (
    <div>
      <AdminPageHeader
        title="Tools"
        subtitle="Ferramentas registradas no Tool Registry. Clique numa linha para ver o schema JSON completo."
      />
      <Card>
        <CardContent className="pt-4">
          {isLoading ? (
            <LoadingRows count={8} />
          ) : isError ? (
            <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
          ) : (
            <ToolTable tools={data ?? []} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
