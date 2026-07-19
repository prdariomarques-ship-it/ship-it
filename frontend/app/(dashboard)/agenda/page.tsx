"use client";

import { useState } from "react";

import PageHeader from "@/components/PageHeader";
import ResourceTable from "@/components/ResourceTable";
import CalendarEventForm from "@/components/calendar/CalendarEventForm";

export default function AgendaPage() {
  const [showForm, setShowForm] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <>
      <PageHeader title="Agenda" subtitle="Seus eventos e compromissos." />

      <button
        className="button"
        type="button"
        onClick={() => setShowForm((v) => !v)}
        style={{ marginBottom: "1.25rem" }}
      >
        {showForm ? "Cancelar" : "Novo evento"}
      </button>

      {showForm && (
        <CalendarEventForm
          onCreated={() => {
            setShowForm(false);
            setRefreshKey((k) => k + 1);
          }}
        />
      )}

      <ResourceTable
        key={refreshKey}
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
