"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/hooks/useApi";
import type {
  AdminIndex,
  AdminLogEntry,
  AgentAdminInfo,
  ComponentStatus,
  ExecutionEntry,
  ExecutionsPeriod,
  GoogleWorkspaceStatus,
  MemoryStats,
  MetricsSnapshot,
  SystemInfo,
  ToolAdminInfo,
  UserAdminRead,
  WhatsAppStatus,
} from "@/lib/admin-types";

// Polling intervals: the backend exposes cumulative Prometheus counters and
// point-in-time snapshots, not a push/websocket feed (see docs/DASHBOARD.md
// "Gráficos em tempo real") — "real-time" here means short-interval polling,
// same approach LangSmith/Grafana dashboards use for a REST-backed panel.
const LIVE_INTERVAL_MS = 5_000;
const NORMAL_INTERVAL_MS = 30_000;

export function useAdminIndex() {
  return useQuery({
    queryKey: ["admin", "index"],
    queryFn: () => apiFetch<AdminIndex>("/admin"),
    refetchInterval: NORMAL_INTERVAL_MS,
  });
}

export function useAdminStatus() {
  return useQuery({
    queryKey: ["admin", "status"],
    queryFn: () => apiFetch<ComponentStatus[]>("/admin/status"),
    refetchInterval: LIVE_INTERVAL_MS,
  });
}

export function useAdminSystem() {
  return useQuery({
    queryKey: ["admin", "system"],
    queryFn: () => apiFetch<SystemInfo>("/admin/system"),
    refetchInterval: LIVE_INTERVAL_MS,
  });
}

export function useAdminAgents() {
  return useQuery({
    queryKey: ["admin", "agents"],
    queryFn: () => apiFetch<AgentAdminInfo[]>("/admin/agents"),
    refetchInterval: NORMAL_INTERVAL_MS,
  });
}

export function useAdminTools() {
  return useQuery({
    queryKey: ["admin", "tools"],
    queryFn: () => apiFetch<ToolAdminInfo[]>("/admin/tools"),
    refetchInterval: NORMAL_INTERVAL_MS,
  });
}

export interface AdminLogsFilters {
  source?: string;
  level?: string;
  search?: string;
  limit?: number;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

export function useAdminLogs(filters: AdminLogsFilters) {
  return useQuery({
    queryKey: ["admin", "logs", filters],
    queryFn: () =>
      apiFetch<AdminLogEntry[]>(
        `/admin/logs${buildQuery({ source: filters.source, level: filters.level, search: filters.search, limit: filters.limit ?? 100 })}`
      ),
    refetchInterval: NORMAL_INTERVAL_MS,
  });
}

export function useAdminGoogle() {
  return useQuery({
    queryKey: ["admin", "google"],
    queryFn: () => apiFetch<GoogleWorkspaceStatus>("/admin/google"),
    refetchInterval: NORMAL_INTERVAL_MS,
  });
}

export function useAdminMemory() {
  return useQuery({
    queryKey: ["admin", "memory"],
    queryFn: () => apiFetch<MemoryStats>("/admin/memory"),
    refetchInterval: NORMAL_INTERVAL_MS,
  });
}

export interface AdminExecutionsFilters {
  period: ExecutionsPeriod;
  agent?: string;
}

export function useAdminExecutions(filters: AdminExecutionsFilters) {
  return useQuery({
    queryKey: ["admin", "executions", filters],
    queryFn: () =>
      apiFetch<ExecutionEntry[]>(
        `/admin/executions${buildQuery({ period: filters.period, agent: filters.agent })}`
      ),
    refetchInterval: NORMAL_INTERVAL_MS,
  });
}

export function useAdminUsers() {
  return useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => apiFetch<UserAdminRead[]>("/admin/users"),
    refetchInterval: NORMAL_INTERVAL_MS,
  });
}

export function useAdminMetrics() {
  return useQuery({
    queryKey: ["admin", "metrics"],
    queryFn: () => apiFetch<MetricsSnapshot>("/admin/metrics"),
    refetchInterval: LIVE_INTERVAL_MS,
  });
}

export function useAdminWhatsApp() {
  return useQuery({
    queryKey: ["admin", "whatsapp"],
    queryFn: () => apiFetch<WhatsAppStatus>("/admin/whatsapp"),
    refetchInterval: LIVE_INTERVAL_MS,
  });
}
