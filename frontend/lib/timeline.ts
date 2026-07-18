// Memory & Timeline — turns the raw `logs` audit trail (plus messages,
// tasks, calendar, goals already fetched elsewhere) into an *operational
// memory*: grouped, explained, and curated — not a flat log viewer. Same
// "no black box" discipline as lib/operator.ts: every event's summary,
// reason and consequence come straight from real field values, never an
// LLM guess. See MEMORY_TIMELINE.md.

import type {
  AdminLogEntry,
  CalendarEventRead,
  GoalRead,
  MessageRead,
  TaskRead,
} from "@/lib/admin-types";
import { formatDateTime } from "@/lib/format";

export type Actor = "user" | "ai" | "system";

export type TimelineSection =
  | "recent_conversations"
  | "goal_progress"
  | "task_progress"
  | "calendar_changes"
  | "whatsapp_activity"
  | "ai_decisions"
  | "system_events"
  | "observation_engine";

export interface TimelineEvent {
  id: string;
  timestamp: string;
  actor: Actor;
  category: TimelineSection;
  summary: string;
  reason: string;
  relatedEntities: string[];
  consequence: string;
  suggestedFollowUp?: string;
  /** 0-100, same tier-based (not fabricated-precision) scoring as
   * lib/operator.ts's confidence — see MEMORY_TIMELINE.md. */
  importance: number;
}

export type TimelineFilter = "today" | "yesterday" | "7d" | "30d" | "everything";

export interface TimelineInput {
  logs: AdminLogEntry[];
  messages: MessageRead[];
  goals: GoalRead[];
  tasks: TaskRead[];
  calendarEvents: CalendarEventRead[];
}

function startOfDay(date: Date): Date {
  const d = new Date(date);
  d.setUTCHours(0, 0, 0, 0);
  return d;
}

/** What date range (if any) a filter maps to. `undefined` bounds mean "no
 * limit in that direction" — `everything` is both undefined. `yesterday`
 * needs a real calendar-day range (start of yesterday to start of today),
 * which a trailing timedelta (like /admin/executions's `period`) can't
 * express — this is why /admin/logs gained real `since`/`until` params. */
export function filterRange(filter: TimelineFilter, now: Date): { since?: Date; until?: Date } {
  const today = startOfDay(now);
  switch (filter) {
    case "today":
      return { since: today };
    case "yesterday":
      return { since: new Date(today.getTime() - 86_400_000), until: today };
    case "7d":
      return { since: new Date(now.getTime() - 7 * 86_400_000) };
    case "30d":
      return { since: new Date(now.getTime() - 30 * 86_400_000) };
    case "everything":
      return {};
  }
}

const PRIORITY_LABEL: Record<string, string> = { low: "baixa", medium: "média", high: "alta", urgent: "urgente" };

// --- Goal events (source: "goal:{id}") ---------------------------------------------
function buildGoalEvent(log: AdminLogEntry): TimelineEvent {
  const p = log.payload as {
    goal_id?: number;
    title?: string;
    status?: string;
    priority?: string;
    progress_percent?: number;
    detail?: string;
  };
  const title = p.title ?? "meta";
  const isRecurrenceSpawn = p.detail === "recurrence";

  let reason = log.message;
  let consequence = "Refletido no painel de Metas.";
  let suggestedFollowUp: string | undefined;

  if (p.status === "awaiting_approval") {
    reason = "Meta criada exigindo aprovação antes de começar.";
    consequence = "A meta não entra na fila até ser aprovada.";
    suggestedFollowUp = "Aprovar ou cancelar a meta pendente.";
  } else if (isRecurrenceSpawn) {
    reason = "Meta recorrente concluída — nova ocorrência criada automaticamente.";
    consequence = "Uma nova meta com o mesmo título entra na fila.";
  } else if (p.status === "completed") {
    reason = "Meta marcada como concluída.";
    consequence = "Uma memória da conclusão foi registrada; a meta sai da fila ativa.";
  } else if (p.status === "cancelled") {
    reason = "Meta cancelada.";
    consequence = "A meta sai da fila ativa sem gerar recorrência.";
  } else if (p.progress_percent !== undefined) {
    reason = `Progresso atualizado para ${p.progress_percent}%.`;
    consequence = "Refletido na pontuação de prioridade da meta.";
  } else if (p.status) {
    reason = `Status mudou para ${p.status}.`;
  }

  return {
    id: `log-${log.id}`,
    timestamp: log.created_at,
    actor: isRecurrenceSpawn ? "system" : "user",
    category: "goal_progress",
    summary: `${title}${p.priority ? ` (prioridade ${PRIORITY_LABEL[p.priority] ?? p.priority})` : ""}`,
    reason,
    relatedEntities: [title],
    consequence,
    suggestedFollowUp,
    importance: p.status === "completed" || p.status === "awaiting_approval" ? 70 : 45,
  };
}

// --- Job events (source: "job:{name}") ----------------------------------------------
function buildJobEvent(log: AdminLogEntry, jobName: string): TimelineEvent {
  const p = log.payload as { job_id?: number; status?: string; detail?: string; attempts?: number };
  const failed = log.level === "error" || p.status === "failed";
  const isWhatsapp = jobName.startsWith("whatsapp.");
  const isCognitive = jobName === "whatsapp.process_inbound";

  return {
    id: `log-${log.id}`,
    timestamp: log.created_at,
    actor: isCognitive ? "ai" : "system",
    category: isWhatsapp ? "whatsapp_activity" : "system_events",
    summary: `${jobName} (${p.status ?? "?"})`,
    reason: failed
      ? `Falhou após ${p.attempts ?? "?"} tentativa(s)${p.detail ? `: ${p.detail}` : ""}.`
      : `Trabalho em segundo plano ${p.status === "succeeded" ? "concluído" : p.status} normalmente.`,
    relatedEntities: [jobName],
    consequence: failed
      ? "O trabalho não foi concluído — pode precisar de nova tentativa manual."
      : "Nenhuma ação necessária.",
    suggestedFollowUp: failed ? "Tentar novamente pelo painel de Jobs Pendentes." : undefined,
    importance: failed ? 80 : 25,
  };
}

// --- Cognitive Pipeline events -------------------------------------------------------
function buildPipelineEvent(log: AdminLogEntry): TimelineEvent {
  const p = log.payload as {
    contact_id?: number;
    intent?: string;
    priority?: string;
    agents?: string[];
    needs_confirmation?: boolean;
    duration_ms?: number;
  };
  const agents = p.agents?.length ? p.agents.join(", ") : "nenhum agente";
  return {
    id: `log-${log.id}`,
    timestamp: log.created_at,
    actor: "ai",
    category: "ai_decisions",
    summary: `Pipeline processou uma mensagem (intenção: ${p.intent ?? "?"})`,
    reason: `Classificada como prioridade ${p.priority ?? "?"}; roteada para ${agents}.`,
    relatedEntities: p.agents ?? [],
    consequence: p.needs_confirmation
      ? "Resposta aguardando confirmação do usuário antes de agir."
      : `Resposta enviada${p.duration_ms ? ` em ${Math.round(p.duration_ms)}ms` : ""}.`,
    suggestedFollowUp: p.needs_confirmation ? "Confirmar ou recusar o plano proposto." : undefined,
    importance: p.needs_confirmation ? 60 : 30,
  };
}

// --- Admin (user) actions ------------------------------------------------------------
function buildAdminActionEvent(log: AdminLogEntry): TimelineEvent {
  const p = log.payload as { job_id?: number; job_name?: string };
  const isCancel = log.source === "admin:job_cancel";
  return {
    id: `log-${log.id}`,
    timestamp: log.created_at,
    actor: "user",
    category: "system_events",
    summary: `Você ${isCancel ? "cancelou" : "reenviou"} o job ${p.job_name ?? p.job_id}`,
    reason: `Ação manual pelo painel administrativo.`,
    relatedEntities: p.job_name ? [p.job_name] : [],
    consequence: isCancel ? "O job não será mais processado." : "O job voltou para a fila.",
    importance: 50,
  };
}

// --- Action Center executions (Phase 4) -----------------------------------------------
/** Every admin:action.* entry is a real execution recorded by
 * hooks/use-action-execution.ts (see ACTION_CENTER.md) — this is the
 * "expose history in the existing Timeline instead of a separate history
 * subsystem" requirement, satisfied entirely by categorizing one more log
 * source prefix, no new storage. */
function buildActionCenterEvent(log: AdminLogEntry): TimelineEvent {
  const p = log.payload as {
    action_type?: string;
    recommendation_title?: string;
    result?: string;
    related_entities?: string[];
    detail?: string | null;
  };
  const succeeded = p.result !== "failure";
  return {
    id: `log-${log.id}`,
    timestamp: log.created_at,
    actor: "user",
    category: "system_events",
    summary: succeeded
      ? `Você executou: ${p.recommendation_title ?? log.message}`
      : `Falha ao executar: ${p.recommendation_title ?? log.message}`,
    reason: "Ação disparada a partir de uma recomendação no Operador IA / Briefing / Central de Ações.",
    relatedEntities: p.related_entities ?? [],
    consequence: succeeded
      ? "A recomendação foi resolvida diretamente pelo painel, sem passos manuais adicionais."
      : `A ação falhou${p.detail ? `: ${p.detail}` : ""} — a recomendação continua pendente.`,
    importance: succeeded ? 40 : 65,
  };
}

// --- WhatsApp session/webhook events -------------------------------------------------
function buildWhatsappInfraEvent(log: AdminLogEntry): TimelineEvent {
  return {
    id: `log-${log.id}`,
    timestamp: log.created_at,
    actor: "system",
    category: "whatsapp_activity",
    summary: log.message,
    reason: "Evento de infraestrutura do gateway WhatsApp.",
    relatedEntities: [],
    consequence: log.level === "error" ? "A sessão pode precisar de reconexão." : "Nenhuma ação necessária.",
    suggestedFollowUp: log.level === "error" ? "Verificar o status da conexão WhatsApp." : undefined,
    importance: log.level === "error" ? 85 : 20,
  };
}

const OBSERVATION_TICK_SOURCE = "job:observation.tick";

/** Every log not specially handled above still becomes a generic system
 * event rather than being silently dropped — curation means judging what's
 * noteworthy, not hiding data. */
function buildGenericEvent(log: AdminLogEntry): TimelineEvent {
  return {
    id: `log-${log.id}`,
    timestamp: log.created_at,
    actor: "system",
    category: "system_events",
    summary: log.message,
    reason: `Registrado por ${log.source}.`,
    relatedEntities: [],
    consequence: "Nenhuma ação necessária.",
    importance: log.level === "error" ? 70 : 15,
  };
}

function buildLogEvents(logs: AdminLogEntry[]): TimelineEvent[] {
  const events: TimelineEvent[] = [];
  for (const log of logs) {
    if (log.source === OBSERVATION_TICK_SOURCE) continue; // rolled up separately, see observationEngineRollup
    if (log.source.startsWith("goal:")) events.push(buildGoalEvent(log));
    else if (log.source.startsWith("job:")) events.push(buildJobEvent(log, log.source.slice("job:".length)));
    else if (log.source === "cognitive_pipeline") events.push(buildPipelineEvent(log));
    else if (log.source.startsWith("admin:action.")) events.push(buildActionCenterEvent(log));
    else if (log.source.startsWith("admin:")) events.push(buildAdminActionEvent(log));
    else if (log.source.startsWith("whatsapp:") || log.source === "webhook:whatsapp")
      events.push(buildWhatsappInfraEvent(log));
    else events.push(buildGenericEvent(log));
  }
  return events;
}

/** observation.tick fires every few minutes — an executive assistant would
 * never narrate "I checked, then I checked again, then I checked again."
 * Rolled into one summary event per call instead of N raw log lines (see
 * docs/OBSERVATION_REVIEW.md's "recent_events dominated by tick noise"
 * limitation — this is where that gets fixed, in the Timeline's own
 * curation, not by changing what the backend logs). A failed tick is still
 * genuinely noteworthy and is never rolled up. */
function observationEngineRollup(logs: AdminLogEntry[], tickSampleLimit: number): TimelineEvent[] {
  const ticks = logs.filter((l) => l.source === OBSERVATION_TICK_SOURCE);
  if (ticks.length === 0) return [];

  const failures = ticks.filter((l) => l.level === "error");
  const events: TimelineEvent[] = [];

  const succeeded = ticks.filter((l) => l.message.includes("succeeded"));
  if (succeeded.length > 0) {
    const latest = succeeded[0];
    // If the tick sample came back exactly at its fetch limit, there may be
    // more beyond it — "N+" is honest about that; an exact "N" would imply
    // completeness we can't actually confirm without fetching everything
    // (which would defeat the point of sampling a high-volume source).
    const possiblyTruncated = ticks.length >= tickSampleLimit;
    const countLabel = possiblyTruncated ? `${succeeded.length}+` : `${succeeded.length}`;
    events.push({
      id: `observation-rollup-${latest.id}`,
      timestamp: latest.created_at,
      actor: "system",
      category: "observation_engine",
      summary: `${countLabel} observação(ões) do sistema concluída(s) com sucesso`,
      reason: "O Context Observation Engine atualiza o snapshot em intervalos regulares.",
      relatedEntities: [],
      consequence: "Contexto Atual mantido em dia automaticamente.",
      importance: 15,
    });
  }

  for (const failure of failures) {
    events.push({
      id: `log-${failure.id}`,
      timestamp: failure.created_at,
      actor: "system",
      category: "observation_engine",
      summary: "Observação do sistema falhou",
      reason: failure.message,
      relatedEntities: [],
      consequence: "O Contexto Atual pode estar desatualizado até a próxima tentativa.",
      suggestedFollowUp: "Verificar os logs do backend para a causa da falha.",
      importance: 75,
    });
  }

  return events;
}

// --- Conversations (from Messages, not logs — richer, real content) -----------------
function buildConversationEvents(messages: MessageRead[]): TimelineEvent[] {
  return messages.map((message) => ({
    id: `message-${message.id}`,
    timestamp: message.created_at,
    // Outbound messages are Dario OS speaking on the owner's behalf (manual
    // send or auto-reply) — both attributed to "ai" here since Messages
    // alone can't distinguish which; inbound is the contact reaching out,
    // an external event this system just observed, hence "system".
    actor: message.direction === "inbound" ? "system" : "ai",
    category: "recent_conversations",
    summary:
      message.direction === "inbound"
        ? `Mensagem recebida do contato ${message.contact_id}`
        : `Mensagem enviada ao contato ${message.contact_id}`,
    reason: message.content.length > 140 ? `${message.content.slice(0, 140)}…` : message.content,
    relatedEntities: [`contato ${message.contact_id}`],
    consequence:
      message.direction === "inbound"
        ? "Pode acionar uma resposta automática do Cognitive Pipeline."
        : "Registrada na memória de curto prazo do contato.",
    importance: 20,
  }));
}

// --- Task Progress (proxy from Task.created_at/updated_at — no task event log exists
// in this codebase, see MEMORY_TIMELINE.md "Known limitations") ------------------------
function buildTaskEvents(tasks: TaskRead[], since: Date | undefined): TimelineEvent[] {
  const events: TimelineEvent[] = [];
  for (const task of tasks) {
    const createdAt = new Date(task.created_at);
    if (!since || createdAt >= since) {
      events.push({
        id: `task-created-${task.id}`,
        timestamp: task.created_at,
        actor: "user",
        category: "task_progress",
        summary: `Tarefa criada: ${task.title}`,
        reason: "Adicionada à lista de tarefas.",
        relatedEntities: [task.title],
        consequence: task.due_date ? `Prazo definido para ${new Date(task.due_date).toLocaleDateString("pt-BR")}.` : "Sem prazo definido.",
        importance: 25,
      });
    }
    if (task.status === "done") {
      const completedAt = new Date(task.updated_at);
      if (!since || completedAt >= since) {
        events.push({
          id: `task-done-${task.id}`,
          timestamp: task.updated_at,
          actor: "user",
          category: "task_progress",
          summary: `Tarefa concluída: ${task.title}`,
          reason: "Status mudou para concluída.",
          relatedEntities: [task.title],
          consequence: "Removida da lista de tarefas pendentes.",
          importance: 40,
        });
      }
    }
  }
  return events;
}

// --- Calendar Changes (proxy from CalendarEvent.created_at/updated_at — same
// limitation as Task Progress: no calendar-event event log exists) ---------------------
function buildCalendarEvents(events: CalendarEventRead[], since: Date | undefined): TimelineEvent[] {
  const results: TimelineEvent[] = [];
  for (const event of events) {
    const createdAt = new Date(event.created_at);
    const updatedAt = new Date(event.updated_at);
    // Whether it was ever modified after creation is independent of whether
    // a `since` filter happens to be active — the two conditions used to be
    // conflated (an undefined `since` made the "created" branch always win),
    // which silently hid every "updated" event outside a date-filtered view.
    const wasModified = updatedAt.getTime() !== createdAt.getTime();

    if (!wasModified) {
      if (!since || createdAt >= since) {
        results.push({
          id: `calendar-created-${event.id}`,
          timestamp: event.created_at,
          actor: "user",
          category: "calendar_changes",
          summary: `Evento criado: ${event.title}`,
          reason: `Agendado para ${formatDateTime(event.starts_at)}.`,
          relatedEntities: [event.title],
          consequence: "Adicionado à agenda.",
          importance: 25,
        });
      }
    } else if (!since || updatedAt >= since) {
      // Best-effort "changed" signal — we know *that* it changed (updated_at
      // moved), not *what* changed (no field-level history exists).
      results.push({
        id: `calendar-updated-${event.id}`,
        timestamp: event.updated_at,
        actor: "user",
        category: "calendar_changes",
        summary: `Evento atualizado: ${event.title}`,
        reason: "Um ou mais campos do evento foram alterados (detalhe exato não registrado).",
        relatedEntities: [event.title],
        consequence: "Revise o evento para confirmar o horário atual.",
        importance: 30,
      });
    }
  }
  return results;
}

/** `tickSampleLimit` must match whatever limit the caller used to fetch
 * `job:observation.tick` rows specifically (see MEMORY_TIMELINE.md — the
 * Timeline fetches tick activity as its own bounded, separate query so it
 * can never crowd out real events) — it's only used to decide whether the
 * rollup count should be shown as exact or as "N+" (possibly truncated). */
export function buildTimelineEvents(
  input: TimelineInput,
  since?: Date,
  tickSampleLimit = 500
): TimelineEvent[] {
  return [
    ...buildLogEvents(input.logs),
    ...observationEngineRollup(input.logs, tickSampleLimit),
    ...buildConversationEvents(input.messages),
    ...buildTaskEvents(input.tasks, since),
    ...buildCalendarEvents(input.calendarEvents, since),
  ].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
}

export function groupBySection(events: TimelineEvent[]): Partial<Record<TimelineSection, TimelineEvent[]>> {
  const grouped: Partial<Record<TimelineSection, TimelineEvent[]>> = {};
  for (const event of events) {
    (grouped[event.category] ??= []).push(event);
  }
  return grouped;
}

/** Events between the start and end of "this morning" (00:00–12:00 UTC,
 * consistent with the rest of the backend's UTC timestamps) — a
 * time-of-day slice across categories, not a new data source. Only
 * meaningful for "today"/"yesterday" filters; returns [] otherwise since
 * "morning" only makes sense for a single day. */
export function morningActivity(events: TimelineEvent[], referenceDay: Date): TimelineEvent[] {
  const dayStart = startOfDay(referenceDay);
  const noon = new Date(dayStart.getTime() + 12 * 3_600_000);
  return events.filter((event) => {
    const t = new Date(event.timestamp).getTime();
    return t >= dayStart.getTime() && t < noon.getTime();
  });
}

export function mostImportantChanges(events: TimelineEvent[], limit = 5): TimelineEvent[] {
  return [...events].sort((a, b) => b.importance - a.importance).slice(0, limit);
}

export interface ChangeSummary {
  label: string;
  totalEvents: number;
  byCategory: Partial<Record<TimelineSection, number>>;
  highlights: TimelineEvent[];
}

/** The direct answer to "what changed since X?" — a count-by-category plus
 * the highest-importance highlights, not a re-dump of every event (that's
 * still available below, grouped by section). */
export function summarizeChanges(events: TimelineEvent[], since: Date, label: string): ChangeSummary {
  const relevant = events.filter((event) => new Date(event.timestamp).getTime() >= since.getTime());
  const byCategory: Partial<Record<TimelineSection, number>> = {};
  for (const event of relevant) {
    byCategory[event.category] = (byCategory[event.category] ?? 0) + 1;
  }
  return {
    label,
    totalEvents: relevant.length,
    byCategory,
    highlights: mostImportantChanges(relevant, 5),
  };
}
