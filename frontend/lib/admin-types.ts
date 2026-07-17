// Mirrors backend/admin/schemas.py exactly — field names, nullability and
// all. Keep these two files in sync by hand; there is no shared codegen in
// this project (see docs/DASHBOARD.md).

export interface ComponentStatus {
  name: string;
  online: boolean;
  detail: string;
  latency_ms: number | null;
  last_heartbeat: string | null;
}

export interface SystemInfo {
  app_name: string;
  version: string;
  environment: string;
  commit: string | null;
  branch: string | null;
  tag: string | null;
  uptime_seconds: number;
  cpu_percent: number | null;
  memory_used_mb: number | null;
  memory_total_mb: number | null;
  memory_percent: number | null;
  disk_used_gb: number | null;
  disk_total_gb: number | null;
  disk_percent: number | null;
  db_pool_size: number | null;
  db_pool_checked_out: number | null;
  llm_provider: string;
  embedding_provider: string;
  whatsapp_provider: string;
  mail_provider: string;
  calendar_provider: string;
  contacts_provider: string;
  drive_provider: string;
  auto_reply_enabled: boolean;
  jobs_enabled: boolean;
}

export interface AgentAdminInfo {
  name: string;
  description: string;
  tool_count: number;
  runs_total: number | null;
  runs_ok: number | null;
  runs_error: number | null;
  avg_duration_seconds: number | null;
  last_execution: string | null;
}

export interface ToolAdminInfo {
  name: string;
  description: string;
  category: string;
  agents: string[];
  parameters: Record<string, unknown>;
  permissions: string | null;
  calls_total: number | null;
  calls_ok: number | null;
  calls_error: number | null;
  last_call: string | null;
}

export interface AdminLogEntry {
  id: number;
  level: string;
  source: string;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface GoogleAccountInfo {
  user_id: number;
  label: string;
  scopes: string[];
  connected_at: string;
}

export interface GoogleDomainStatus {
  domain: string;
  connected_accounts: number;
  accounts: GoogleAccountInfo[];
  indexed_items: number | null;
  last_indexed_at: string | null;
}

export interface GoogleWorkspaceStatus {
  mail: GoogleDomainStatus;
  calendar: GoogleDomainStatus;
  contacts: GoogleDomainStatus;
  drive: GoogleDomainStatus;
}

export interface MemoryCollectionStats {
  name: string;
  points_count: number | null;
  vectors_count: number | null;
  status: string | null;
}

export interface MemoryStats {
  collection: MemoryCollectionStats;
  embeddings_total: number;
  embeddings_by_source: Record<string, number>;
  drive_indexed_files: number;
  drive_last_indexed_at: string | null;
  cache_backend: string;
}

export interface ExecutionEntry {
  kind: "job" | "log";
  id: number;
  timestamp: string;
  name: string;
  agent: string | null;
  status: string;
  detail: string;
  duration_seconds: number | null;
}

export interface UserAdminRead {
  id: number;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface WhatsAppStatus {
  provider: string;
  connected: boolean;
  detail: string;
  queue_depth: number;
  messages_sent: number;
  messages_received: number;
}

export interface AdminIndex {
  users_total: number;
  agents_total: number;
  tools_total: number;
  google_connected_accounts: number;
  whatsapp_connected: boolean;
  uptime_seconds: number;
}

export interface PrometheusSample {
  name: string;
  labels: Record<string, string>;
  value: number;
}

export interface MetricsSnapshot {
  timestamp: string;
  metrics: Record<string, PrometheusSample[]>;
}

export type ExecutionsPeriod = "today" | "24h" | "7d" | "30d";

// --- Context Observation Engine (backend/observation/) -----------------------------
// Mirrors backend/observation/models.py::ContextItem / CurrentContext exactly.
export interface ContextItem {
  source: string;
  content: string;
}

export interface CurrentContext {
  user_id: number;
  generated_at: string;
  trigger: string;
  goals: ContextItem[];
  tasks: ContextItem[];
  calendar: ContextItem[];
  recent_events: ContextItem[];
  conversations: ContextItem[];
  pending_work: ContextItem[];
  memory: ContextItem[];
  degraded_sources: string[];
}

// --- Goals / Tasks / Calendar (mirrors goals/router.py, api/schemas.py) ------------
export type GoalStatus =
  | "awaiting_approval"
  | "pending"
  | "in_progress"
  | "completed"
  | "cancelled";
export type GoalPriority = "low" | "medium" | "high" | "urgent";

export interface GoalRead {
  id: number;
  user_id: number;
  title: string;
  description: string | null;
  status: GoalStatus;
  priority: GoalPriority;
  deadline: string | null;
  progress_percent: number;
  requires_approval: boolean;
  approved_at: string | null;
  approved_by_id: number | null;
  recurrence_interval_days: number | null;
  recurrence_parent_id: number | null;
  created_at: string;
  updated_at: string;
}

export type TaskStatus = "pending" | "in_progress" | "done" | "cancelled";
export type TaskPriority = "low" | "medium" | "high";

export interface TaskRead {
  id: number;
  user_id: number;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface CalendarEventRead {
  id: number;
  user_id: number;
  title: string;
  description: string | null;
  location: string | null;
  starts_at: string;
  ends_at: string | null;
  reminder_minutes: number | null;
  created_at: string;
  updated_at: string;
}

// --- Jobs (mirrors jobs/router.py::JobRead) -----------------------------------------
export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface JobRead {
  id: number;
  name: string;
  payload: Record<string, unknown>;
  status: JobStatus;
  attempts: number;
  max_attempts: number;
  scheduled_at: string;
  started_at: string | null;
  finished_at: string | null;
  last_error: string | null;
  created_at: string;
}

// --- Messages (mirrors api/schemas.py::MessageRead) ---------------------------------
export type MessageDirection = "inbound" | "outbound";

export interface MessageRead {
  id: number;
  contact_id: number;
  direction: MessageDirection;
  media_type: string;
  content: string;
  external_id: string | null;
  created_at: string;
  updated_at: string;
}
