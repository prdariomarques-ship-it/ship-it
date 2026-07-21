"use client";

import { useEffect, useState } from "react";

import PageHeader from "@/components/PageHeader";
import ResourceTable from "@/components/ResourceTable";
import ChurchMemberForm from "@/components/church/ChurchMemberForm";

export default function IgrejaPage() {
  const [showForm, setShowForm] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");

  // Debounced live search: waits 250ms after the last keystroke before
  // hitting the API, so typing doesn't fire a request per character.
  useEffect(() => {
    const timeout = setTimeout(() => setQuery(searchInput), 250);
    return () => clearTimeout(timeout);
  }, [searchInput]);

  const path = query ? `/church/members?q=${encodeURIComponent(query)}` : "/church/members";

  return (
    <>
      <PageHeader
        title="Igreja"
        subtitle="Membros, escalas, pedidos de oração e avisos."
      />

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem", flexWrap: "wrap" }}>
        <button
          className="button"
          type="button"
          onClick={() => setShowForm((v) => !v)}
        >
          {showForm ? "Cancelar" : "Novo membro"}
        </button>
        <input
          className="input"
          placeholder="Buscar membro por nome…"
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
          style={{ flex: 1, minWidth: "200px", marginBottom: 0 }}
          aria-label="Buscar membro por nome"
        />
      </div>

      {showForm && (
        <ChurchMemberForm
          onCreated={() => {
            setShowForm(false);
            setRefreshKey((k) => k + 1);
          }}
        />
      )}

      <ResourceTable
        key={`${refreshKey}-${path}`}
        path={path}
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
        emptyMessage={query ? "Nenhum membro encontrado para essa busca." : "Nenhum membro cadastrado."}
      />
    </>
  );
}
