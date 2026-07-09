"use client";

import PageHeader from "@/components/PageHeader";
import StatCard from "@/components/StatCard";
import { useApi } from "@/hooks/useApi";

export default function AnalyticsPage() {
  const { data, loading, error } = useApi<Record<string, number>>(
    "/dashboard/summary"
  );

  return (
    <>
      <PageHeader
        title="Analytics"
        subtitle="Métricas consolidadas de todos os módulos."
      />
      {loading && <p className="muted">Carregando…</p>}
      {error && <p className="error">Erro: {error}</p>}
      {data && (
        <div className="stat-grid">
          {Object.entries(data).map(([key, value]) => (
            <StatCard key={key} label={key.replace(/_/g, " ")} value={value} />
          ))}
        </div>
      )}
    </>
  );
}
