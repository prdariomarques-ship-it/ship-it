"use client";

import { useState } from "react";

import PageHeader from "@/components/PageHeader";
import GoalForm from "@/components/goals/GoalForm";
import { apiFetch, useApi } from "@/hooks/useApi";

interface Goal {
  id: number;
  title: string;
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
                <tr key={goal.id}>
                  <td>{goal.title}</td>
                  <td>
                    <span className="badge">{STATUS_LABELS[goal.status] ?? goal.status}</span>
                  </td>
                  <td>{PRIORITY_LABELS[goal.priority] ?? goal.priority}</td>
                  <td>{goal.deadline ?? "—"}</td>
                  <td>{goal.progress_percent}%</td>
                  <td>
                    {isAdmin && goal.status === "awaiting_approval" ? (
                      <button
                        className="button"
                        type="button"
                        disabled={approvingId === goal.id}
                        onClick={() => handleApprove(goal.id)}
                      >
                        {approvingId === goal.id ? "Aprovando…" : "Aprovar"}
                      </button>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
