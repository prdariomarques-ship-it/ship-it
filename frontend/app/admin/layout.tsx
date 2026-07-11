import type { Metadata } from "next";

import "@/styles/admin.css";
import { AdminShell } from "@/components/admin/AdminShell";

export const metadata: Metadata = {
  title: "Dario OS — Admin",
  description: "Dashboard administrativo do Dario OS",
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AdminShell>{children}</AdminShell>;
}
