"use client";

import PageHeader from "@/components/PageHeader";
import ResourceTable from "@/components/ResourceTable";

export default function ConversasPage() {
  return (
    <>
      <PageHeader
        title="Conversas"
        subtitle="Mensagens recebidas e enviadas pelo WhatsApp."
      />
      <ResourceTable
        path="/messages"
        columns={[
          { key: "id", label: "#" },
          { key: "contact_id", label: "Contato" },
          {
            key: "direction",
            label: "Direção",
            render: (value) => (
              <span className="badge">
                {value === "inbound" ? "Recebida" : "Enviada"}
              </span>
            ),
          },
          { key: "media_type", label: "Tipo" },
          { key: "content", label: "Conteúdo" },
          { key: "created_at", label: "Data" },
        ]}
        emptyMessage="Nenhuma conversa ainda. Conecte o OpenWA para começar."
      />
    </>
  );
}
