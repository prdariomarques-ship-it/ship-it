"use client";

import { useState } from "react";

import { ApprovalsTab } from "@/components/darius/ApprovalsTab";
import { LogsTab } from "@/components/darius/LogsTab";
import { MetricsTab } from "@/components/darius/MetricsTab";
import { OverviewTab } from "@/components/darius/OverviewTab";
import { PausedTab } from "@/components/darius/PausedTab";
import { SuspensionTab } from "@/components/darius/SuspensionTab";
import { TelegramTab } from "@/components/darius/TelegramTab";
import { TasksTab } from "@/components/darius/TasksTab";
import { WhatsAppTab } from "@/components/darius/WhatsAppTab";
import { cn } from "@/lib/utils";

export type DariusTabId =
  | "overview"
  | "tasks"
  | "approvals"
  | "metrics"
  | "whatsapp"
  | "paused"
  | "telegram"
  | "suspension"
  | "logs";

const TABS: Array<{ id: DariusTabId; label: string }> = [
  { id: "overview", label: "Visão geral" },
  { id: "tasks", label: "Tarefas" },
  { id: "approvals", label: "Aprovações" },
  { id: "metrics", label: "Métricas" },
  { id: "whatsapp", label: "WhatsApp" },
  { id: "paused", label: "Conversas pausadas" },
  { id: "telegram", label: "Telegram" },
  { id: "suspension", label: "Suspensão" },
  { id: "logs", label: "Logs" },
];

export function DariusPanel({ initialTab = "overview" }: { initialTab?: DariusTabId }) {
  const [tab, setTab] = useState<DariusTabId>(initialTab);

  return (
    <div className="flex flex-col gap-4">
      <div role="tablist" aria-label="Seções do painel DARIUS" className="flex flex-wrap gap-1 border-b border-border">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`darius-tab-${item.id}`}
            aria-selected={tab === item.id}
            aria-controls={`darius-panel-${item.id}`}
            onClick={() => setTab(item.id)}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              tab === item.id
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`darius-panel-${tab}`} aria-labelledby={`darius-tab-${tab}`}>
        {tab === "overview" ? <OverviewTab onOpen={setTab} /> : null}
        {tab === "tasks" ? <TasksTab /> : null}
        {tab === "approvals" ? <ApprovalsTab /> : null}
        {tab === "metrics" ? <MetricsTab /> : null}
        {tab === "whatsapp" ? <WhatsAppTab /> : null}
        {tab === "paused" ? <PausedTab /> : null}
        {tab === "telegram" ? <TelegramTab /> : null}
        {tab === "suspension" ? <SuspensionTab /> : null}
        {tab === "logs" ? <LogsTab /> : null}
      </div>
    </div>
  );
}
