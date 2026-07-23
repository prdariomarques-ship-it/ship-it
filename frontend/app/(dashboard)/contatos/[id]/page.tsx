"use client";

import { useParams } from "next/navigation";
import { useRef, useState } from "react";

import PageHeader from "@/components/PageHeader";
import { apiFetch, useApi } from "@/hooks/useApi";

interface WorkspaceMessage {
  id: number;
  direction: "inbound" | "outbound";
  content: string;
  created_at: string;
}

interface WorkspaceNote {
  id: number;
  title: string;
  content: string;
  pinned: boolean;
  created_at: string;
}

interface WorkspaceTask {
  id: number;
  title: string;
  status: string;
  priority: string;
  due_date: string | null;
  created_at: string;
}

interface WorkspaceEvent {
  id: number;
  title: string;
  starts_at: string;
  location: string | null;
}

interface TimelineEntry {
  id: string;
  type: "message" | "note" | "task" | "meeting";
  timestamp: string;
  title: string;
  subtitle: string | null;
  status: string | null;
  source: string;
  metadata: Record<string, unknown>;
}

interface RelationshipSignal {
  code: string;
  kind: "risk" | "opportunity";
  severity: "urgent" | "attention" | "info";
  reason: string;
}

interface RelationshipStatus {
  tier: "healthy" | "cooling" | "cold" | "at_risk";
  score: number;
  signals: RelationshipSignal[];
}

interface WorkspaceSummary {
  id: number;
  name: string;
  phone: string | null;
  categories: string[];
  tags: string[];
  last_interaction_at: string | null;
  relationship_status: RelationshipStatus;
  suggested_next_action: string;
  ai_summary: string | null;
  memory: Record<string, unknown>;
}

interface CurrentState {
  open_tasks: WorkspaceTask[];
  upcoming_events: WorkspaceEvent[];
  pending_follow_ups: WorkspaceMessage[];
  important_notes: WorkspaceNote[];
}

interface Recommendation {
  id: string;
  type: "follow_up" | "check_pending_tasks";
  priority: "urgent" | "attention";
  confidence: number;
  explanation: string;
  reasoning: string[];
  supporting_signals: string[];
  confirmation_required: boolean;
  execution_target: string | null;
  execution_payload: Record<string, unknown> | null;
  created_at: string;
  expires_at: string | null;
}

interface ContactWorkspace {
  summary: WorkspaceSummary;
  timeline: TimelineEntry[];
  current_state: CurrentState;
  recommendations: Recommendation[];
}

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("pt-BR");
}

const TIMELINE_LABELS: Record<TimelineEntry["type"], string> = {
  message: "Mensagem",
  note: "Nota",
  task: "Tarefa",
  meeting: "Reunião",
};

const RELATIONSHIP_TIER_LABELS: Record<RelationshipStatus["tier"], string> = {
  healthy: "Saudável",
  cooling: "Esfriando",
  cold: "Fria",
  at_risk: "Em risco",
};

const RECOMMENDATION_PRIORITY_LABELS: Record<Recommendation["priority"], string> = {
  urgent: "Urgente",
  attention: "Atenção",
};

export default function ContactWorkspacePage() {
  const params = useParams<{ id: string }>();
  const { data, loading, error, reload } = useApi<ContactWorkspace>(
    `/contacts/${params.id}/workspace`
  );

  // Release 1.5 hardening (red-team audit): `executingIdsRef` is the real
  // guard against double-execution -- a plain ref mutates synchronously,
  // so a second click (even one that fires before React commits the
  // disabled-button re-render) sees the id already present and bails out
  // immediately. `executingIds` (state) exists only to drive the UI
  // (disabled attribute, "Executando…" label) -- it is never the guard
  // itself. A Set (not a single id) supports more than one recommendation
  // executing at once, independently -- a single scalar here previously
  // meant a second recommendation's click could silently clear the first
  // one's disabled state while its request was still in flight. Entries are
  // recommendation ids, always formatted `${contactId}-${type}` by the
  // backend (contacts/recommendations.py) -- unique across contacts, so a
  // stale entry left behind by an in-flight request from a previously
  // viewed contact can never match a different contact's recommendation id.
  const executingIdsRef = useRef<Set<string>>(new Set());
  const [executingIds, setExecutingIds] = useState<Set<string>>(new Set());
  const [executeError, setExecuteError] = useState<string | null>(null);

  // Release 1.5 hardening (red-team audit, FIX 4): `executeError` must
  // never survive a navigation to a different contact -- a failure on
  // contact A must not linger as a banner on contact B's page. Adjusted
  // during render (React's documented pattern for resetting state when a
  // prop changes -- react.dev/learn/you-might-not-need-an-effect
  // #adjusting-some-state-when-a-prop-changes) rather than in a
  // `useEffect`, which would call setState synchronously inside the effect
  // body and cause an extra, avoidable render pass. Only plain state is
  // touched here, never the ref (see above) -- mutating a ref during render
  // is itself unsafe and unnecessary given the id-uniqueness guarantee.
  const [renderedContactId, setRenderedContactId] = useState(params.id);
  if (params.id !== renderedContactId) {
    setRenderedContactId(params.id);
    setExecutingIds(new Set());
    setExecuteError(null);
  }

  async function handleExecute(recommendationId: string) {
    if (executingIdsRef.current.has(recommendationId)) return;
    executingIdsRef.current.add(recommendationId);
    setExecutingIds(new Set(executingIdsRef.current));
    setExecuteError(null);
    try {
      await apiFetch(`/contacts/${params.id}/recommendations/${recommendationId}/execute`, {
        method: "POST",
      });
      reload();
    } catch (err) {
      setExecuteError(
        err instanceof Error ? err.message : "Falha ao executar recomendação"
      );
    } finally {
      executingIdsRef.current.delete(recommendationId);
      setExecutingIds(new Set(executingIdsRef.current));
    }
  }

  if (loading) return <p className="muted">Carregando…</p>;
  if (error) return <p className="error">Erro: {error}</p>;
  if (!data) return null;

  const { summary, timeline, current_state: currentState, recommendations } = data;

  return (
    <>
      <PageHeader title={summary.name} subtitle={summary.phone ?? undefined} />

      {/* 1. Resumo do relacionamento -- quem é, quando falamos, o que fazer a seguir */}
      <div className="card">
        <h3 style={{ marginBottom: "0.5rem" }}>Resumo do relacionamento</h3>
        <p className="muted">
          Categorias: {summary.categories.length > 0 ? summary.categories.join(", ") : "—"}
        </p>
        <p className="muted">
          Tags: {summary.tags.length > 0 ? summary.tags.join(", ") : "—"}
        </p>
        <p className="muted">
          Última interação: {formatDateTime(summary.last_interaction_at)}
        </p>
        <p className="muted">
          Status do relacionamento:{" "}
          {RELATIONSHIP_TIER_LABELS[summary.relationship_status.tier]}
        </p>
        {summary.relationship_status.signals.length > 0 && (
          <ul>
            {summary.relationship_status.signals.map((signal) => (
              <li key={signal.code} className="muted">
                {signal.reason}
              </li>
            ))}
          </ul>
        )}
        <p className="muted">
          Próxima ação sugerida: {summary.suggested_next_action}
        </p>
        <p>{summary.ai_summary ?? "Ainda sem resumo gerado."}</p>
      </div>

      {/* 2. Linha do tempo -- WhatsApp, notas, tarefas e reuniões, mais recente primeiro */}
      <div className="card">
        <h3 style={{ marginBottom: "0.5rem" }}>Linha do tempo</h3>
        {timeline.length === 0 ? (
          <p className="muted">Nada registrado ainda.</p>
        ) : (
          <ul>
            {timeline.map((entry) => (
              <li key={entry.id}>
                <span className="badge">{TIMELINE_LABELS[entry.type]}</span>{" "}
                {entry.title}
                {entry.subtitle ? ` — ${entry.subtitle}` : ""}{" "}
                <span className="muted">({formatDateTime(entry.timestamp)})</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 3. Estado atual -- tarefas abertas, próximos eventos, follow-ups pendentes, notas importantes */}
      <div className="card">
        <h3 style={{ marginBottom: "0.5rem" }}>Tarefas pendentes</h3>
        {currentState.open_tasks.length === 0 ? (
          <p className="muted">Nenhuma tarefa vinculada a este contato.</p>
        ) : (
          <ul>
            {currentState.open_tasks.map((task) => (
              <li key={task.id}>
                <strong>{task.title}</strong> — {task.status}{" "}
                {task.due_date ? `(prazo ${formatDateTime(task.due_date)})` : ""}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <h3 style={{ marginBottom: "0.5rem" }}>Próximos eventos</h3>
        {currentState.upcoming_events.length === 0 ? (
          <p className="muted">Nenhum evento futuro vinculado a este contato.</p>
        ) : (
          <ul>
            {currentState.upcoming_events.map((event) => (
              <li key={event.id}>
                <strong>{event.title}</strong> — {formatDateTime(event.starts_at)}
                {event.location ? ` (${event.location})` : ""}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <h3 style={{ marginBottom: "0.5rem" }}>Follow-ups pendentes</h3>
        {currentState.pending_follow_ups.length === 0 ? (
          <p className="muted">Nenhuma resposta enviada recentemente.</p>
        ) : (
          <ul>
            {currentState.pending_follow_ups.map((message) => (
              <li key={message.id}>
                {message.content} <span className="muted">({formatDateTime(message.created_at)})</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <h3 style={{ marginBottom: "0.5rem" }}>Notas importantes</h3>
        {currentState.important_notes.length === 0 ? (
          <p className="muted">Nenhuma nota vinculada a este contato.</p>
        ) : (
          <ul>
            {currentState.important_notes.map((note) => (
              <li key={note.id}>
                {note.pinned ? "📌 " : ""}
                <strong>{note.title}</strong> — {note.content}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 4. Ações -- recomendações determinísticas do P0-4 (contacts/recommendations.py) */}
      <div className="card">
        <h3 style={{ marginBottom: "0.5rem" }}>Ações sugeridas</h3>
        {executeError && <p className="error">{executeError}</p>}
        {recommendations.length === 0 ? (
          <p className="muted">Nenhuma recomendação disponível ainda.</p>
        ) : (
          <ul>
            {recommendations.map((recommendation) => (
              <li key={recommendation.id} style={{ marginBottom: "0.75rem" }}>
                <span className="badge">
                  {RECOMMENDATION_PRIORITY_LABELS[recommendation.priority]}
                </span>{" "}
                {recommendation.explanation}{" "}
                <span className="muted">
                  (confiança {recommendation.confidence}%)
                </span>
                {recommendation.confirmation_required && (
                  <div style={{ marginTop: "0.35rem" }}>
                    <button
                      className="button"
                      type="button"
                      disabled={executingIds.has(recommendation.id)}
                      onClick={() => handleExecute(recommendation.id)}
                    >
                      {executingIds.has(recommendation.id) ? "Executando…" : "Executar"}
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
