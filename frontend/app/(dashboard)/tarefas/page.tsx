"use client";

import PageHeader from "@/components/PageHeader";
import ResourceTable from "@/components/ResourceTable";

const STATUS_LABELS: Record<string, string> = {
  pending: "Pendente",
  in_progress: "Em andamento",
  done: "Concluída",
  cancelled: "Cancelada",
};

export default function TarefasPage() {
  return (
    <>
      <PageHeader title="Tarefas" subtitle="Tudo o que precisa ser feito." />
      <ResourceTable
        path="/tasks"
        columns={[
          { key: "title", label: "Tarefa" },
          {
            key: "status",
            label: "Status",
            render: (value) => (
              <span className="badge">{STATUS_LABELS[String(value)] ?? String(value)}</span>
            ),
          },
          { key: "priority", label: "Prioridade" },
          { key: "due_date", label: "Prazo" },
        ]}
        emptyMessage="Nenhuma tarefa cadastrada."
      />
    </>
  );
}
