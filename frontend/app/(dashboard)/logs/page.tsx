"use client";

import PageHeader from "@/components/PageHeader";
import ResourceTable from "@/components/ResourceTable";

export default function LogsPage() {
  return (
    <>
      <PageHeader title="Logs" subtitle="Auditoria de eventos do sistema." />
      <ResourceTable
        path="/logs"
        columns={[
          { key: "created_at", label: "Data" },
          {
            key: "level",
            label: "Nível",
            render: (value) => <span className="badge">{String(value)}</span>,
          },
          { key: "source", label: "Origem" },
          { key: "message", label: "Mensagem" },
        ]}
        emptyMessage="Nenhum log registrado."
      />
    </>
  );
}
