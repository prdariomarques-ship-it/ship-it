"use client";

import Link from "next/link";
import { ArrowLeft, Menu } from "lucide-react";

import { useAdminStatus } from "@/lib/admin-api";

interface AdminHeaderProps {
  userEmail: string;
  onToggleSidebar?: () => void;
}

export function AdminHeader({ userEmail, onToggleSidebar }: AdminHeaderProps) {
  const { data: status } = useAdminStatus();
  const backend = status?.find((item) => item.name === "backend");
  const allOnline = status?.every((item) => item.online) ?? null;

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-card/60 px-4 sm:px-6">
      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        <button
          type="button"
          aria-label="Abrir menu"
          onClick={onToggleSidebar}
          className="rounded-md p-1.5 hover:bg-accent hover:text-foreground md:hidden"
        >
          <Menu className="h-4 w-4" />
        </button>
        <Link href="/" className="flex items-center gap-1.5 hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Voltar ao app</span>
        </Link>
      </div>
      <div className="flex items-center gap-4 text-sm">
        <div className="flex items-center gap-1.5">
          {/* Dot stays visible at every width — it's the one piece of this
              row a mobile user actually needs (is something wrong right
              now?). The label text next to it, plus the heartbeat and the
              email below, were all unconditionally visible and wrapped onto
              a second line on narrow screens, colliding with the
              hamburger/back icons (HOMOLOGATION_REPORT_v1.3.1.md). */}
          <span
            className={
              "h-2 w-2 shrink-0 rounded-full " +
              (allOnline === null ? "bg-muted-foreground" : allOnline ? "bg-success" : "bg-destructive")
            }
          />
          <span className="hidden text-muted-foreground sm:inline">
            {allOnline === null ? "verificando…" : allOnline ? "todos os sistemas operacionais" : "atenção necessária"}
          </span>
        </div>
        {backend?.last_heartbeat ? (
          <span className="hidden text-xs text-muted-foreground sm:inline">
            heartbeat {new Date(backend.last_heartbeat).toLocaleTimeString("pt-BR")}
          </span>
        ) : null}
        <span className="hidden text-muted-foreground sm:inline">{userEmail}</span>
      </div>
    </header>
  );
}
