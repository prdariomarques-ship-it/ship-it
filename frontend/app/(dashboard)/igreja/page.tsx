"use client";

import { useState } from "react";

import PageHeader from "@/components/PageHeader";
import ResourceTable from "@/components/ResourceTable";
import ChurchMemberForm from "@/components/church/ChurchMemberForm";

export default function IgrejaPage() {
  const [showForm, setShowForm] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <>
      <PageHeader
        title="Igreja"
        subtitle="Membros, escalas, pedidos de oração e avisos."
      />

      <button
        className="button"
        type="button"
        onClick={() => setShowForm((v) => !v)}
        style={{ marginBottom: "1.25rem" }}
      >
        {showForm ? "Cancelar" : "Novo membro"}
      </button>

      {showForm && (
        <ChurchMemberForm
          onCreated={() => {
            setShowForm(false);
            setRefreshKey((k) => k + 1);
          }}
        />
      )}

      <ResourceTable
        key={refreshKey}
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
