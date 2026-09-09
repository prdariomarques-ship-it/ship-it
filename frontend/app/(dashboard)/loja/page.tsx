"use client";

import { useState } from "react";

import PageHeader from "@/components/PageHeader";
import ResourceTable from "@/components/ResourceTable";
import StoreCustomerForm from "@/components/store/StoreCustomerForm";
import ProductsPanel from "@/components/store/ProductsPanel";

type LojaTab = "clientes" | "produtos";

export default function LojaPage() {
  const [tab, setTab] = useState<LojaTab>("clientes");
  const [showForm, setShowForm] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <>
      <PageHeader
        title="Loja"
        subtitle="Clientes, catálogo, orçamentos e pedidos do seu negócio."
      />

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
        <button
          className="button"
          type="button"
          onClick={() => setTab("clientes")}
          style={{ opacity: tab === "clientes" ? 1 : 0.55 }}
          aria-pressed={tab === "clientes"}
        >
          Clientes
        </button>
        <button
          className="button"
          type="button"
          onClick={() => setTab("produtos")}
          style={{ opacity: tab === "produtos" ? 1 : 0.55 }}
          aria-pressed={tab === "produtos"}
        >
          Produtos
        </button>
      </div>

      {tab === "clientes" && (
        <>
          <button
            className="button"
            type="button"
            onClick={() => setShowForm((v) => !v)}
            style={{ marginBottom: "1.25rem" }}
          >
            {showForm ? "Cancelar" : "Novo cliente"}
          </button>

          {showForm && (
            <StoreCustomerForm
              onCreated={() => {
                setShowForm(false);
                setRefreshKey((k) => k + 1);
              }}
            />
          )}

          <ResourceTable
            key={refreshKey}
            path="/store/customers"
            columns={[
              { key: "name", label: "Cliente" },
              { key: "phone", label: "Telefone" },
              { key: "email", label: "E-mail" },
              {
                key: "segment",
                label: "Segmento",
                render: (value) => (value ? String(value) : "—"),
              },
              {
                key: "orders",
                label: "Pedidos",
                render: (value) => String(Array.isArray(value) ? value.length : 0),
              },
            ]}
            emptyMessage="Nenhum cliente cadastrado."
          />
        </>
      )}

      {tab === "produtos" && <ProductsPanel />}
    </>
  );
}
