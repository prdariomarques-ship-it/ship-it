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
  /** Why a task ended/stalled. Absent on runtimes that predate the retry classification. */
  failureClass?: DariusFailureClass | null;
  /** Present only while a QUEUED task waits for its next automatic attempt. */
  retry?: { attempts: number; nextAttemptAt: number | null } | null;
}

export type DariusFailureClass =
  | "BEFORE_EFFECT_TRANSIENT"
  | "BEFORE_EFFECT_PERMANENT"
  | "EFFECT_UNKNOWN"
  | "EFFECT_CONFIRMED"
  | "RETRIES_EXHAUSTED";

// --- Runtime metrics (GET /admin/darius/metrics). Open dictionaries on purpose: the engine adds counters
// over time and the panel must keep working; a counter that is missing is shown as "indisponível". ---

export interface RuntimeMetrics {
  generatedAt: number;
  scope: Record<string, unknown>;
  tasks: { available?: boolean; total?: number; byStatus?: Record<string, number> } & Record<string, unknown>;
  queue: { queued?: number; backingOff?: number; nextRetryAt?: number | null } & Record<string, unknown>;
  engine: Record<string, unknown>;
  scheduler: { enabled?: boolean } & Record<string, unknown>;
}

// --- Conversations a human took over (GET /admin/darius/paused-conversations). Phone is masked server-side. ---

export interface PausedConversation {
  contact_id: number;
  contact_name: string | null;
  phone_tail: string | null;
  instance: string;
  revision: number;
  paused_since: string | null;
  reason: string | null;
  actor_id: number | null;
  send_in_flight: boolean;
}

export interface PausedConversationPage {
  items: PausedConversation[];
  total: number;
  next_offset: number | null;
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

// --- Telegram: audited, static inventory (GET /admin/telegram/bots). Never live state. ---

export type TelegramRuntimeStatus = "ativo_evidenciado" | "sem_agendamento" | "nao_verificado" | "inconclusivo";

export interface TelegramTrigger {
  kind: "schedule" | "manual" | "continuous";
  expression: string | null;
  host: string;
}

export interface TelegramRuntime {
  status: TelegramRuntimeStatus;
  detail: string;
  evidence: string | null;
  as_of: string | null;
}

export interface TelegramBot {
  id: string;
  name: string;
  scope: "ship-it" | "externo";
  repository: string | null;
  source_files: string[];
  kind: "command_poller" | "push_report" | "gateway" | "unknown";
  purpose: string;
  commands: string[];
  data_sources: string[];
  /** Environment variable NAMES only. */
  credentials: string[];
  triggers: TelegramTrigger[];
  runtime: TelegramRuntime;
  risks: string[];
}

export interface TelegramInventory {
  as_of: string;
  live_state_available: boolean;
  live_state_note: string;
  bots: TelegramBot[];
  counts_by_runtime_status: Record<string, number>;
}
