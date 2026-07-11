"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { useAdminStatus } from "@/lib/admin-api";

export function AdminHeader({ userEmail }: { userEmail: string }) {
  const { data: status } = useAdminStatus();
  const backend = status?.find((item) => item.name === "backend");
  const allOnline = status?.every((item) => item.online) ?? null;

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-card/60 px-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link href="/" className="flex items-center gap-1.5 hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" />
          Voltar ao app
        </Link>
      </div>
      <div className="flex items-center gap-4 text-sm">
        <div className="flex items-center gap-1.5">
          <span
            className={
              "h-2 w-2 rounded-full " +
              (allOnline === null ? "bg-muted-foreground" : allOnline ? "bg-success" : "bg-destructive")
            }
          />
          <span className="text-muted-foreground">
            {allOnline === null ? "verificando…" : allOnline ? "todos os sistemas operacionais" : "atenção necessária"}
          </span>
        </div>
        {backend?.last_heartbeat ? (
          <span className="hidden text-xs text-muted-foreground sm:inline">
            heartbeat {new Date(backend.last_heartbeat).toLocaleTimeString("pt-BR")}
          </span>
        ) : null}
        <span className="text-muted-foreground">{userEmail}</span>
      </div>
    </header>
  );
}
