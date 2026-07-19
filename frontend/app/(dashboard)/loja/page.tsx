"use client";

import { useState } from "react";

import PageHeader from "@/components/PageHeader";
import ResourceTable from "@/components/ResourceTable";
import StoreCustomerForm from "@/components/store/StoreCustomerForm";

export default function LojaPage() {
  const [showForm, setShowForm] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <>
      <PageHeader
        title="Loja"
        subtitle="Clientes, pedidos e orçamentos do seu negócio."
      />

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
            key: "orders",
            label: "Pedidos",
            render: (value) => String(Array.isArray(value) ? value.length : 0),
          },
        ]}
        emptyMessage="Nenhum cliente cadastrado."
      />
    </>
  );
}
