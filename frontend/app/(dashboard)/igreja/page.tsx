"use client";

import PageHeader from "@/components/PageHeader";
import ResourceTable from "@/components/ResourceTable";

export default function IgrejaPage() {
  return (
    <>
      <PageHeader
        title="Igreja"
        subtitle="Membros, escalas, pedidos de oração e avisos."
      />
      <ResourceTable
        path="/church/members"
        columns={[
          { key: "name", label: "Membro" },
          { key: "role", label: "Função" },
          {
            key: "ministries",
            label: "Ministérios",
            render: (value) =>
              Array.isArray(value) && value.length > 0 ? value.join(", ") : "—",
          },
          {
            key: "prayer_requests",
            label: "Pedidos de oração",
            render: (value) => String(Array.isArray(value) ? value.length : 0),
          },
        ]}
        emptyMessage="Nenhum membro cadastrado."
      />
    </>
  );
}
