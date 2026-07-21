"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/hooks/useApi";
import type {
  AdminIndex,
  AdminLogEntry,
  AgentAdminInfo,
  CalendarEventRead,
  ComponentStatus,
  CurrentContext,
  ExecutionEntry,
  ExecutionsPeriod,
  GoalRead,
  GoogleWorkspaceStatus,
  JobRead,
  JobStatus,
  MemorySearchResult,
  MemoryStats,
  MessageRead,
  MetricsSnapshot,
  SettingInfo,
  SystemInfo,
  TaskRead,
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

export function useAdminSettings() {
  return useQuery({
    queryKey: ["admin", "settings"],
    queryFn: () => apiFetch<SettingInfo[]>("/admin/settings"),
    refetchInterval: NORMAL_INTERVAL_MS,
  });
}

export function updateAdminSetting(key: string, value: boolean | number | string) {
  return apiFetch<SettingInfo>("/admin/settings", {
    method: "PATCH",
    body: JSON.stringify({ key, value }),
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
  sourcePrefix?: string;
  excludeSource?: string;
  level?: string;
  search?: string;
  since?: string;
  until?: string;
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
        `/admin/logs${buildQuery({
          source: filters.source,
          source_prefix: filters.sourcePrefix,
          exclude_source: filters.excludeSource,
          level: filters.level,
          search: filters.search,
          since: filters.since,
          until: filters.until,
          limit: filters.limit ?? 100,
        })}`
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

// Not an /admin/* endpoint -- /memory/search is the general memory router
// (no admin gate on the backend), only surfaced on this admin-only page.
// `enabled` gates on a non-empty query so this never fires until the user
// actually submits a search.
export function useMemorySearch(query: string, contactId?: number) {
  return useQuery({
    queryKey: ["memory", "search", query, contactId],
    queryFn: () =>
      apiFetch<MemorySearchResult[]>(
        `/memory/search${buildQuery({ q: query, contact_id: contactId })}`
      ),
    enabled: query.trim().length > 0,
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

// --- Operational Dashboard: CurrentContext (observation/), Goals, Tasks, Calendar,
// Jobs. All reuse endpoints that already existed before this dashboard — the only
// net-new backend surface is GET /admin/observation itself (a thin read over the
// already-built Context Observation Engine, see docs/OBSERVATION_ENGINE.md).

export function useAdminObservation() {
  return useQuery({
    queryKey: ["admin", "observation"],
    queryFn: () => apiFetch<CurrentContext>("/admin/observation"),
    refetchInterval: LIVE_INTERVAL_MS,
  });
}

export function useReadyGoals() {
  return useQuery({
    queryKey: ["goals", "ready"],
    queryFn: () => apiFetch<GoalRead[]>("/goals/ready"),
    refetchInterval: NORMAL_INTERVAL_MS,
  });
}

export function useGoalsAwaitingApproval() {
  return useQuery({
    queryKey: ["goals", "awaiting_approval"],
    queryFn: () => apiFetch<GoalRead[]>("/goals?status=awaiting_approval"),
    refetchInterval: NORMAL_INTERVAL_MS,
  });
}

export function useTasks() {
  return useQuery({
    queryKey: ["tasks"],
    queryFn: () => apiFetch<TaskRead[]>("/tasks?limit=200"),
    refetchInterval: NORMAL_INTERVAL_MS,
  });
}

export function useCalendarEvents() {
  return useQuery({
    queryKey: ["calendar"],
    queryFn: () => apiFetch<CalendarEventRead[]>("/calendar?limit=200"),
    refetchInterval: NORMAL_INTERVAL_MS,
  });
}

export function useJobsByStatus(status: JobStatus) {
  return useQuery({
    queryKey: ["jobs", status],
    queryFn: () => apiFetch<JobRead[]>(`/jobs?status=${status}&limit=50`),
    refetchInterval: LIVE_INTERVAL_MS,
  });
}

// --- Memory & Timeline (Phase 2): reuses /messages (existing) and the
// since/until extension to /admin/logs (the one backend change this phase
// needed) — see MEMORY_TIMELINE.md.

export function useRecentMessages(limit = 200) {
  return useQuery({
    queryKey: ["messages", limit],
    queryFn: () => apiFetch<MessageRead[]>(`/messages?limit=${limit}`),
    refetchInterval: NORMAL_INTERVAL_MS,
  });
}

/** Every goal regardless of status (not just `ready`) — the Timeline needs
 * completed/cancelled goals too, unlike the Operator Center's ready-only view. */
export function useAllGoals() {
  return useQuery({
    queryKey: ["goals", "all"],
    queryFn: () => apiFetch<GoalRead[]>("/goals?limit=200"),
    refetchInterval: NORMAL_INTERVAL_MS,
  });
}
