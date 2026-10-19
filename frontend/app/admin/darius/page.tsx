"use client";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { DariusPanel } from "@/components/darius/DariusPanel";

export default function AdminDariusPage() {
  return (
    <div>
      <AdminPageHeader
        title="DARIUS"
        subtitle="Tarefas, aprovações, fluxo WhatsApp→DARIUS e suspensão da automação, com dados reais do backend."
      />
      <DariusPanel />
    </div>
  );
}
