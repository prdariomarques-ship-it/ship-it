"use client";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { AgentCard } from "@/components/admin/AgentCard";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { EmptyState } from "@/components/admin/EmptyState";
import { useAdminAgents } from "@/lib/admin-api";

export default function AdminAgentsPage() {
  const { data, isLoading, isError, error, refetch } = useAdminAgents();

  return (
    <div>
      <AdminPageHeader
        title="Agents"
        subtitle="Agentes registrados no Agent Registry, com estatísticas quando disponíveis."
      />
      {isLoading ? (
        <LoadingGrid count={5} />
      ) : isError ? (
        <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
      ) : !data || data.length === 0 ? (
        <EmptyState title="Nenhum agente registrado" />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((agent) => (
            <AgentCard key={agent.name} agent={agent} />
          ))}
        </div>
      )}
    </div>
  );
}
