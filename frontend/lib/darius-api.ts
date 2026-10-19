"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/hooks/useApi";
import { useAdminLogs } from "@/lib/admin-api";
import type { AdminLogEntry } from "@/lib/admin-types";
import type {
  ApiErrorDetail,
  DariusDecision,
  DariusDecisionAck,
  DariusStatus,
  PausedConversationPage,
  RuntimeMetrics,
  DariusTaskPage,
  DariusTaskResult,
  DariusTaskState,
  DariusTaskStatus,
  SuspensionState,
  TelegramInventory,
  WhatsAppLinkPage,
  WhatsAppRouting,
} from "@/lib/darius-types";

// Short-interval polling, same approach as lib/admin-api.ts: the backend is REST-only.
const LIVE_INTERVAL_MS = 10_000;

function query(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const dariusKeys = {
  all: ["darius"] as const,
  status: ["darius", "status"] as const,
  tasks: ["darius", "tasks"] as const,
  whatsapp: ["darius", "whatsapp"] as const,
  suspension: ["darius", "suspension"] as const,
  telegram: ["darius", "telegram"] as const,
  metrics: ["darius", "metrics"] as const,
  paused: ["darius", "paused"] as const,
};

export function useRuntimeMetrics() {
  return useQuery({
    queryKey: dariusKeys.metrics,
    queryFn: () => apiFetch<RuntimeMetrics>("/admin/darius/metrics"),
    refetchInterval: LIVE_INTERVAL_MS,
  });
}

export interface PausedConversationFilters {
  instance?: string;
  limit?: number;
  offset?: number;
}

export function usePausedConversations(filters: PausedConversationFilters) {
  return useQuery({
    queryKey: [...dariusKeys.paused, filters],
    queryFn: () =>
      apiFetch<PausedConversationPage>(
        `/admin/darius/paused-conversations${query({
          instance: filters.instance,
          limit: filters.limit ?? 25,
          offset: filters.offset ?? 0,
        })}`
      ),
    refetchInterval: LIVE_INTERVAL_MS,
  });
}

export function useDariusStatus() {
  return useQuery({
    queryKey: dariusKeys.status,
    queryFn: () => apiFetch<DariusStatus>("/admin/darius/status"),
    refetchInterval: LIVE_INTERVAL_MS,
  });
}

export interface DariusTaskFilters {
  status?: DariusTaskStatus;
  limit?: number;
  offset?: number;
}

export function useDariusTasks(filters: DariusTaskFilters) {
  return useQuery({
    queryKey: [...dariusKeys.tasks, "list", filters],
    queryFn: () =>
      apiFetch<DariusTaskPage>(
        `/admin/darius/tasks${query({ status: filters.status, limit: filters.limit ?? 25, offset: filters.offset ?? 0 })}`
      ),
    refetchInterval: LIVE_INTERVAL_MS,
  });
}

export function useDariusTaskDetail(taskId: string | null) {
  return useQuery({
    queryKey: [...dariusKeys.tasks, "detail", taskId],
    enabled: taskId !== null,
    queryFn: async () => {
      const id = encodeURIComponent(taskId as string);
      const [state, result] = await Promise.all([
        apiFetch<DariusTaskState>(`/admin/darius/tasks/${id}`),
        apiFetch<DariusTaskResult>(`/admin/darius/tasks/${id}/result`),
      ]);
      return { state, result };
    },
  });
}

export interface DecisionInput {
  taskId: string;
  decision: DariusDecision;
  reason?: string;
}

export function useDariusDecision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, decision, reason }: DecisionInput) =>
      apiFetch<DariusDecisionAck>(`/admin/darius/tasks/${encodeURIComponent(taskId)}/${decision}`, {
        method: "POST",
        // Only `reject` carries a reason; the bridge ignores a body on the other two.
        body: decision === "reject" ? JSON.stringify({ reason: reason?.trim() || null }) : undefined,
      }),
    // Refetch even on failure: a 409 means the task already moved on, and the list must show where.
    onSettled: () => queryClient.invalidateQueries({ queryKey: dariusKeys.tasks }),
  });
}

export interface WhatsAppLinkFilters {
  status?: string;
  instance?: string;
  limit?: number;
  offset?: number;
}

export function useWhatsAppLinks(filters: WhatsAppLinkFilters) {
  return useQuery({
    queryKey: [...dariusKeys.whatsapp, "links", filters],
    queryFn: () =>
      apiFetch<WhatsAppLinkPage>(
        `/admin/darius/whatsapp-tasks${query({
          status: filters.status,
          instance: filters.instance,
          limit: filters.limit ?? 25,
          offset: filters.offset ?? 0,
        })}`
      ),
    refetchInterval: LIVE_INTERVAL_MS,
  });
}

export function useWhatsAppRouting() {
  return useQuery({
    queryKey: [...dariusKeys.whatsapp, "routing"],
    queryFn: () => apiFetch<WhatsAppRouting>("/admin/darius/whatsapp-routing"),
    refetchInterval: LIVE_INTERVAL_MS,
  });
}

/** Audited static inventory; it changes only with the code, so it is fetched once per visit. */
export function useTelegramInventory() {
  return useQuery({
    queryKey: dariusKeys.telegram,
    queryFn: () => apiFetch<TelegramInventory>("/admin/telegram/bots"),
    staleTime: 5 * 60_000,
  });
}

export function useSuspension() {
  return useQuery({
    queryKey: dariusKeys.suspension,
    queryFn: () => apiFetch<SuspensionState>("/admin/automation/suspension"),
    refetchInterval: LIVE_INTERVAL_MS,
  });
}

export interface SuspensionInput {
  /** Omit for the global switch. */
  instance?: string;
  suspended: boolean;
  reason: string;
}

export function useSetSuspension() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ instance, suspended, reason }: SuspensionInput) =>
      apiFetch<SuspensionState>(
        instance
          ? `/admin/automation/suspension/instances/${encodeURIComponent(instance)}`
          : "/admin/automation/suspension/global",
        { method: "PUT", body: JSON.stringify({ suspended, reason: reason.trim() }) }
      ),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: dariusKeys.suspension });
      queryClient.invalidateQueries({ queryKey: dariusKeys.whatsapp });
    },
  });
}

/** Audit trail of the integration: DARIUS bridge decisions, the WhatsApp flow and suspensions. */
export function useDariusLogs(limit = 50): {
  entries: AdminLogEntry[];
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
} {
  const darius = useAdminLogs({ sourcePrefix: "darius", limit });
  const suspension = useAdminLogs({ source: "automation_suspension", limit });
  const entries = [...(darius.data ?? []), ...(suspension.data ?? [])]
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    .slice(0, limit);
  return {
    entries,
    isLoading: darius.isLoading || suspension.isLoading,
    isError: darius.isError || suspension.isError,
    error: darius.error ?? suspension.error,
    refetch: () => {
      void darius.refetch();
      void suspension.refetch();
    },
  };
}

export interface ExplainedError {
  message: string;
  hint?: string;
  /** True when DARIUS may have applied the action even though the call failed (never retry blindly). */
  outcomeUnknown: boolean;
}

const HINTS: Record<string, string> = {
  DARIUS_NOT_CONFIGURED: "O DARIUS não está configurado neste backend (URL e credenciais).",
  DARIUS_UNAVAILABLE: "O DARIUS está inacessível ou o circuito está aberto. Tente novamente em instantes.",
  DARIUS_CREDENTIAL_REJECTED: "O DARIUS recusou a credencial do Dario OS: é um problema de configuração.",
  DARIUS_INVALID_RESPONSE: "O DARIUS respondeu algo fora do contrato esperado.",
};

/** Turns an `apiFetch` failure into something an operator can act on. Never invents a cause. */
export function explainError(error: unknown): ExplainedError {
  if (!(error instanceof Error)) return { message: "Erro desconhecido", outcomeUnknown: false };
  // Duck-typed on purpose (see ApiError in hooks/useApi.ts): works for any error carrying `status`/`detail`.
  const { status, detail } = error as Error & { status?: unknown; detail?: unknown };
  const info = (typeof detail === "object" && detail !== null && !Array.isArray(detail) ? detail : {}) as ApiErrorDetail;
  const conflict = status === 409 ? "A tarefa já mudou de estado; a lista foi atualizada." : undefined;
  return {
    message: error.message,
    hint: (info.code ? HINTS[info.code] : undefined) ?? conflict,
    outcomeUnknown: info.outcome_unknown === true,
  };
}
