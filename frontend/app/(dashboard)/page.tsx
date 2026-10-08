"use client";

import Link from "next/link";
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

// "Mercados em primeiro plano" vem de DESIGN.md/INTEGRATION_STATUS.md: a
// visão geral apresenta as duas frentes financeiras antes do resumo
// operacional, com indisponibilidade explícita (nenhuma cotação real
// ainda) — mas o resumo real existente (useApi("/dashboard/summary")) e
// seus estados de carregamento/erro continuam intactos abaixo, não
// substituídos por conteúdo fictício.
export default function HomePage() {
  const { data, loading, error } = useApi<Summary>("/dashboard/summary");

  return (
    <>
      <PageHeader
        title="Visão geral"
        subtitle="Mercados, panorama operacional e módulos do Darius OS num único lugar."
      />

      <div className="card">
        <h2 className="page-title" style={{ fontSize: "1rem" }}>
          Mercados
        </h2>
        <p className="muted" style={{ marginBottom: "0.75rem" }}>
          Duas frentes independentes para o contexto financeiro.
        </p>
        <div className="empty-state">
          <span className="badge badge-stale" style={{ flexShrink: 0 }}>
            Sem dado ao vivo
          </span>
          <div>
            <strong>Nenhuma fonte de mercado conectada ainda</strong>
            <Link href="/mercado-brasil" className="muted" style={{ display: "block", marginTop: "4px" }}>
              Abrir Mercado · Brasil →
            </Link>
            <Link href="/mercado-global" className="muted" style={{ display: "block", marginTop: "2px" }}>
              Abrir Mercado Global →
            </Link>
          </div>
        </div>
      </div>

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
