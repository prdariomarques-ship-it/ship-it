"use client";

import PageHeader from "@/components/PageHeader";
import StatCard from "@/components/StatCard";
import { useApi } from "@/hooks/useApi";

interface Summary {
  contacts: number;
  messages: number;
  pending_tasks: number;
  notes: number;
  events: number;
  church_members: number;
  store_customers: number;
}

export default function HomePage() {
  const { data, loading, error } = useApi<Summary>("/dashboard/summary");

  return (
    <>
      <PageHeader
        title="Início"
        subtitle="Visão geral do seu sistema operacional pessoal."
      />
      {loading && <p className="muted">Carregando…</p>}
      {error && <p className="error">Erro: {error}</p>}
      {data && (
        <div className="stat-grid">
          <StatCard label="Contatos" value={data.contacts} />
          <StatCard label="Mensagens" value={data.messages} />
          <StatCard label="Tarefas pendentes" value={data.pending_tasks} />
          <StatCard label="Notas" value={data.notes} />
          <StatCard label="Eventos" value={data.events} />
          <StatCard label="Membros (igreja)" value={data.church_members} />
          <StatCard label="Clientes (loja)" value={data.store_customers} />
        </div>
      )}
    </>
  );
}
