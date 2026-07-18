"use client";

import { useRef, useState } from "react";

import { AdminHeader } from "@/components/admin/AdminHeader";
import { AdminSidebar } from "@/components/admin/AdminSidebar";
import { AdminQueryProvider } from "@/components/admin/QueryProvider";
import { AdminToastProvider } from "@/hooks/use-toast";
import { useAdminGuard } from "@/hooks/use-admin-guard";
import { PortalContainerProvider } from "@/hooks/use-portal-container";

function GuardScreen({ children }: { children: React.ReactNode }) {
  const state = useAdminGuard();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  if (state.status === "loading") {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">
        Verificando permissões…
      </div>
    );
  }

  if (state.status === "denied") {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-2 text-center">
        <h1 className="text-lg font-semibold">Acesso restrito</h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          O Dashboard Administrativo é exclusivo para usuários com papel ADMIN.
        </p>
        <a href="/" className="mt-2 text-sm text-primary hover:underline">
          Voltar ao app
        </a>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <AdminSidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <AdminHeader userEmail={state.user.email} onToggleSidebar={() => setSidebarOpen((open) => !open)} />
        <main className="admin-scroll flex-1 overflow-y-auto p-4 sm:p-6" tabIndex={0}>
          {children}
        </main>
      </div>
    </div>
  );
}

export function AdminShell({ children }: { children: React.ReactNode }) {
  const themeRootRef = useRef<HTMLDivElement>(null);

  return (
    <div className="admin-theme" ref={themeRootRef}>
      <PortalContainerProvider containerRef={themeRootRef}>
        <AdminQueryProvider>
          <AdminToastProvider>
            <GuardScreen>{children}</GuardScreen>
          </AdminToastProvider>
        </AdminQueryProvider>
      </PortalContainerProvider>
    </div>
  );
}
