"use client";

import { useState } from "react";

import PageHeader from "@/components/PageHeader";
import ResourceTable from "@/components/ResourceTable";
import TaskForm from "@/components/tasks/TaskForm";

const STATUS_LABELS: Record<string, string> = {
  pending: "Pendente",
  in_progress: "Em andamento",
  done: "Concluída",
  cancelled: "Cancelada",
};

export default function TarefasPage() {
  const [showForm, setShowForm] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <>
      <PageHeader title="Tarefas" subtitle="Tudo o que precisa ser feito." />

      <button
        className="button"
        type="button"
        onClick={() => setShowForm((v) => !v)}
        style={{ marginBottom: "1.25rem" }}
      >
        {showForm ? "Cancelar" : "Nova tarefa"}
      </button>

      {showForm && (
        <TaskForm
          onCreated={() => {
            setShowForm(false);
            setRefreshKey((k) => k + 1);
          }}
        />
      )}

      <ResourceTable
        key={refreshKey}
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
