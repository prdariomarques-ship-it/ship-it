"use client";

import PageHeader from "@/components/PageHeader";
import ResourceTable from "@/components/ResourceTable";

const STATUS_LABELS: Record<string, string> = {
  awaiting_approval: "Aguardando aprovação",
  pending: "Pendente",
  in_progress: "Em andamento",
  completed: "Concluída",
  cancelled: "Cancelada",
};

const PRIORITY_LABELS: Record<string, string> = {
  low: "Baixa",
  medium: "Média",
  high: "Alta",
  urgent: "Urgente",
};

export default function MetasPage() {
  return (
    <>
      <PageHeader
        title="Metas"
        subtitle="Objetivos com prazo, dependências e prioridade — diferente de uma tarefa simples."
      />
      <ResourceTable
        path="/goals"
        columns={[
          { key: "title", label: "Meta" },
          {
            key: "status",
            label: "Status",
            render: (value) => (
              <span className="badge">{STATUS_LABELS[String(value)] ?? String(value)}</span>
            ),
          },
          {
            key: "priority",
            label: "Prioridade",
            render: (value) => PRIORITY_LABELS[String(value)] ?? String(value),
          },
          { key: "deadline", label: "Prazo" },
          {
            key: "progress_percent",
            label: "Progresso",
            render: (value) => `${String(value ?? 0)}%`,
          },
        ]}
        emptyMessage="Nenhuma meta cadastrada."
      />
    </>
  );
}
