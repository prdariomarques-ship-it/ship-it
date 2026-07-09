"use client";

import PageHeader from "@/components/PageHeader";
import ResourceTable from "@/components/ResourceTable";

export default function LojaPage() {
  return (
    <>
      <PageHeader
        title="Loja"
        subtitle="Clientes, pedidos e orçamentos do seu negócio."
      />
      <ResourceTable
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
