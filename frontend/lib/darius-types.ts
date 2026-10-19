// Mirrors backend/admin/darius.py, backend/admin/automation.py and services/darius_client.py.
// Nothing here is invented client-side: every field comes from an admin endpoint and a missing
// value stays `null` / `undefined` so the UI can say "indisponível" instead of showing a made-up number.

export type DariusTaskStatus =
  | "PENDING"
  | "QUEUED"
  | "RUNNING"
  | "PAUSED"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export const DARIUS_TASK_STATUSES: DariusTaskStatus[] = [
  "PENDING",
  "QUEUED",
  "RUNNING",
  "PAUSED",
  "COMPLETED",
  "FAILED",
  "CANCELLED",
];

export interface DariusStatus {
  configured: boolean;
  reachable: boolean;
  circuit: string;
  latency_ms: number | null;
  base_url: string;
  service_credential_configured: boolean;
  operator_credential_configured: boolean;
  checked_at: string;
  error: string | null;
}

export interface DariusTaskSummary {
  id: string;
  objective: string;
  status: DariusTaskStatus;
  agentId?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface DariusTaskPage {
  items: DariusTaskSummary[];
  total: number;
  next_offset: number | null;
}

export interface DariusTraceStep {
  state: string;
  timestamp?: string | null;
  output?: string | null;
  error?: string | null;
}

export interface DariusTaskState {
  taskId: string;
  objective: string;
  status: DariusTaskStatus;
  currentState?: string | null;
  iterations: number;
  trace: DariusTraceStep[];
}

export interface DariusTaskResult {
  id: string;
  status: DariusTaskStatus;
  done: boolean;
  result?: string | null;
  error?: string | null;
  updatedAt: string;
}

export interface DariusDecisionAck {
  id: string;
  status: DariusTaskStatus;
  decision?: "APPROVED" | "REJECTED" | null;
}

export type DariusDecision = "approve" | "reject" | "cancel";

export type WhatsAppLinkStatus =
  | "submitting"
  | "submitted"
  | "reply_queued"
  | "failed"
  | "cancelled"
  | "expired"
  | "skipped";

export const WHATSAPP_LINK_STATUSES: WhatsAppLinkStatus[] = [
  "submitting",
  "submitted",
  "reply_queued",
  "failed",
  "cancelled",
  "expired",
  "skipped",
];

export interface WhatsAppLink {
  id: number;
  instance: string;
  status: WhatsAppLinkStatus | string;
  darius_task_id: string | null;
  darius_status: string | null;
  message_id: number;
  contact_id: number;
  attempts: number;
  last_error: string | null;
  reply_chars: number | null;
  history: Array<Record<string, unknown>>;
  created_at: string;
  finished_at: string | null;
}

export interface WhatsAppLinkPage {
  items: WhatsAppLink[];
  counts: Record<string, number>;
  next_offset: number | null;
}

export interface WhatsAppInstanceRouting {
  instance: string;
  routed_to_darius: boolean;
  suspended: boolean;
  suspension_reason: string | null;
}

export interface WhatsAppRouting {
  enabled: boolean;
  darius_configured: boolean;
  reply_timeout_seconds: number;
  global_suspended: boolean;
  global_suspension_reason: string | null;
  instances: WhatsAppInstanceRouting[];
  unknown_routed_instances: string[];
}

export interface SuspensionDetail {
  scope: string;
  reason: string;
  actor_id: number | null;
  since: string | null;
}

export interface SuspensionState {
  global_suspended: boolean;
  global_forced_by_environment: boolean;
  suspended_instances: string[];
  configured_instances: string[];
  details: SuspensionDetail[];
  changed?: boolean | null;
}

/** Structured error thrown by `apiFetch` (see hooks/useApi.ts). */
export interface ApiErrorDetail {
  message?: string;
  code?: string;
  status?: string;
  outcome_unknown?: boolean;
}
