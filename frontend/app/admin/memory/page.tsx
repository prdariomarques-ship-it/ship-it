"use client";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { MemoryStatsView } from "@/components/admin/MemoryStatsView";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { useAdminMemory } from "@/lib/admin-api";

export default function AdminMemoryPage() {
  const { data, isLoading, isError, error, refetch } = useAdminMemory();

  return (
    <div>
      <AdminPageHeader
        title="Memory"
        subtitle="Coleções do Qdrant, embeddings por origem e status de indexação do Google Drive."
      />
      {isLoading ? (
        <LoadingGrid count={4} />
      ) : isError ? (
        <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
      ) : data ? (
        <MemoryStatsView stats={data} />
      ) : null}
    </div>
  );
}
