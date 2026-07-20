"use client";

import { Fragment, useState } from "react";

import PageHeader from "@/components/PageHeader";
import GoalForm from "@/components/goals/GoalForm";
import GoalDetails from "@/components/goals/GoalDetails";
import { apiFetch, useApi } from "@/hooks/useApi";

interface Goal {
  id: number;
  title: string;
  description: string | null;
  status: string;
  priority: string;
  deadline: string | null;
  progress_percent: number;
}

interface Me {
  role: string;
}

const STATUS_LABELS: Record<string, string> = {
  awaiting_approval: "Aguardando aprovação",
  pending: "Pendente",
  in_progress: "Em andamento",
  completed: "Concluída",
  cancelled: "Cancelada",
};

const PRIORITY_LABELS: Record<string, string> = {
  low: "Baixa",
  medium: "Média",
  high: "Alta",
  urgent: "Urgente",
};

export default function MetasPage() {
  const { data: goals, loading, error, reload } = useApi<Goal[]>("/goals");
  const { data: me } = useApi<Me>("/auth/me");
  const isAdmin = me?.role === "admin";

  const [showForm, setShowForm] = useState(false);
  const [approvingId, setApprovingId] = useState<number | null>(null);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<{ id: number; mode: "edit" | "details" } | null>(
    null
  );

  async function handleApprove(goalId: number) {
    setApprovingId(goalId);
    setApproveError(null);
    try {
      await apiFetch(`/goals/${goalId}/approve`, { method: "POST" });
      reload();
    } catch (err) {
      setApproveError(err instanceof Error ? err.message : "Falha ao aprovar meta");
    } finally {
      setApprovingId(null);
    }
  }

  function toggleExpanded(id: number, mode: "edit" | "details") {
    setExpanded((current) =>
      current && current.id === id && current.mode === mode ? null : { id, mode }
    );
  }

  return (
    <>
      <PageHeader
        title="Metas"
        subtitle="Objetivos com prazo, dependências e prioridade — diferente de uma tarefa simples."
      />

      <button className="button" type="button" onClick={() => setShowForm((v) => !v)} style={{ marginBottom: "1.25rem" }}>
        {showForm ? "Cancelar" : "Nova meta"}
      </button>

      {showForm && (
        <GoalForm
          onCreated={() => {
            setShowForm(false);
            reload();
          }}
        />
      )}

      {approveError && <p className="error">{approveError}</p>}

      {loading && <p className="muted">Carregando…</p>}
      {error && <p className="error">Erro: {error}</p>}
      {!loading && !error && (!goals || goals.length === 0) && (
        <p className="muted">Nenhuma meta cadastrada.</p>
      )}

      {!loading && !error && goals && goals.length > 0 && (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Meta</th>
                <th>Status</th>
                <th>Prioridade</th>
                <th>Prazo</th>
                <th>Progresso</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {goals.map((goal) => (
                <Fragment key={goal.id}>
                  <tr>
                    <td>{goal.title}</td>
                    <td>
                      <span className="badge">{STATUS_LABELS[goal.status] ?? goal.status}</span>
                    </td>
                    <td>{PRIORITY_LABELS[goal.priority] ?? goal.priority}</td>
                    <td>{goal.deadline ?? "—"}</td>
                    <td>{goal.progress_percent}%</td>
                    <td style={{ display: "flex", gap: "0.5rem" }}>
                      {isAdmin && goal.status === "awaiting_approval" && (
                        <button
                          className="button"
                          type="button"
                          disabled={approvingId === goal.id}
                          onClick={() => handleApprove(goal.id)}
                        >
                          {approvingId === goal.id ? "Aprovando…" : "Aprovar"}
                        </button>
                      )}
                      <button
                        className="button"
                        type="button"
                        onClick={() => toggleExpanded(goal.id, "edit")}
                      >
                        {expanded?.id === goal.id && expanded.mode === "edit"
                          ? "Fechar"
                          : "Editar"}
                      </button>
                      <button
                        className="button"
                        type="button"
                        onClick={() => toggleExpanded(goal.id, "details")}
                      >
                        {expanded?.id === goal.id && expanded.mode === "details"
                          ? "Fechar"
                          : "Detalhes"}
                      </button>
                    </td>
                  </tr>
                  {expanded?.id === goal.id && expanded.mode === "edit" && (
                    <tr>
                      <td colSpan={6}>
                        <GoalForm
                          goal={goal}
                          onCreated={() => {
                            setExpanded(null);
                            reload();
                          }}
                        />
                      </td>
                    </tr>
                  )}
                  {expanded?.id === goal.id && expanded.mode === "details" && (
                    <tr>
                      <td colSpan={6}>
                        <GoalDetails
                          goal={goal}
                          otherGoals={goals}
                          onChanged={() => {
                            reload();
                          }}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
