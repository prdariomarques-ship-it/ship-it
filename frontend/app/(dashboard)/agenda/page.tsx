"use client";

import PageHeader from "@/components/PageHeader";
import ResourceTable from "@/components/ResourceTable";

export default function AgendaPage() {
  return (
    <>
      <PageHeader title="Agenda" subtitle="Seus eventos e compromissos." />
      <ResourceTable
        path="/calendar"
        columns={[
          { key: "title", label: "Evento" },
          { key: "location", label: "Local" },
          { key: "starts_at", label: "Início" },
          { key: "ends_at", label: "Fim" },
        ]}
        emptyMessage="Nenhum evento agendado."
      />
    </>
  );
}
