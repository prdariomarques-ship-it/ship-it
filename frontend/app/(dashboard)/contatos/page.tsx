"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import PageHeader from "@/components/PageHeader";
import ResourceTable from "@/components/ResourceTable";

export default function ContatosPage() {
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");

  // Debounced live search: waits 250ms after the last keystroke before
  // hitting the API, so typing doesn't fire a request per character --
  // same pattern already used by /igreja and /notas.
  useEffect(() => {
    const timeout = setTimeout(() => setQuery(searchInput), 250);
    return () => clearTimeout(timeout);
  }, [searchInput]);

  const path = query
    ? `/contacts?q=${encodeURIComponent(query)}`
    : "/contacts";

  return (
    <>
      <PageHeader
        title="Contatos"
        subtitle="Abra um contato para ver o relacionamento inteiro: conversas, notas, tarefas e agenda em um só lugar."
      />

      <div style={{ marginBottom: "1.25rem" }}>
        <input
          className="input"
          placeholder="Buscar contato por nome…"
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
          style={{ marginBottom: 0 }}
          aria-label="Buscar contato por nome"
        />
      </div>

      <ResourceTable
        path={path}
        columns={[
          {
            key: "name",
            label: "Nome",
            render: (value, row) => (
              <Link href={`/contatos/${row.id}`}>{String(value)}</Link>
            ),
          },
          { key: "phone", label: "Telefone" },
          {
            key: "categories",
            label: "Categorias",
            render: (value) =>
              Array.isArray(value) && value.length > 0 ? value.join(", ") : "—",
          },
          {
            key: "last_interaction_at",
            label: "Última interação",
            render: (value) =>
              value ? new Date(String(value)).toLocaleString("pt-BR") : "—",
          },
        ]}
        emptyMessage="Nenhum contato ainda."
      />
    </>
  );
}
