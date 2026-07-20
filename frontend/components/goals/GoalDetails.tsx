"use client";

import { useState } from "react";

import { apiFetch, useApi } from "@/hooks/useApi";

interface Goal {
  id: number;
  title: string;
  status: string;
}

interface HistoryEntry {
  id: number;
  message: string;
  created_at: string;
}

const CANCELLABLE_STATUSES = new Set(["awaiting_approval", "pending", "in_progress"]);

export default function GoalDetails({
  goal,
  otherGoals,
  onChanged,
}: {
  goal: Goal & { progress_percent: number };
  otherGoals: Goal[];
  onChanged: () => void;
}) {
  const {
    data: dependencies,
    loading: loadingDependencies,
    reload: reloadDependencies,
  } = useApi<Goal[]>(`/goals/${goal.id}/dependencies`);
  const { data: history, loading: loadingHistory } = useApi<HistoryEntry[]>(
    `/goals/${goal.id}/history`
  );

  const [progress, setProgress] = useState(goal.progress_percent);
  const [savingProgress, setSavingProgress] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [dependsOnId, setDependsOnId] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleSaveProgress() {
    setSavingProgress(true);
    setError(null);
    try {
      await apiFetch(`/goals/${goal.id}/progress`, {
        method: "PATCH",
        body: JSON.stringify({ progress_percent: progress }),
      });
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao atualizar progresso");
    } finally {
      setSavingProgress(false);
    }
  }

  async function handleCancel() {
    setCancelling(true);
    setError(null);
    try {
      await apiFetch(`/goals/${goal.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: "cancelled" }),
      });
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao cancelar meta");
    } finally {
      setCancelling(false);
    }
  }

  async function handleAddDependency() {
    if (!dependsOnId) return;
    setError(null);
    try {
      await apiFetch(`/goals/${goal.id}/dependencies`, {
        method: "POST",
        body: JSON.stringify({ depends_on_id: Number(dependsOnId) }),
      });
      setDependsOnId("");
      reloadDependencies();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao adicionar dependência");
    }
  }

  async function handleRemoveDependency(dependsOn: number) {
    setError(null);
    try {
      await apiFetch(`/goals/${goal.id}/dependencies/${dependsOn}`, {
        method: "DELETE",
      });
      reloadDependencies();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao remover dependência");
    }
  }

  const dependencyIds = new Set((dependencies ?? []).map((dep) => dep.id));
  const candidateGoals = otherGoals.filter(
    (candidate) => candidate.id !== goal.id && !dependencyIds.has(candidate.id)
  );

  return (
    <div className="card" aria-label={`Detalhes da meta ${goal.title}`}>
      {error && <p className="error">{error}</p>}

      <div style={{ marginBottom: "1rem" }}>
        <label htmlFor={`progress-${goal.id}`}>Progresso</label>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <input
            id={`progress-${goal.id}`}
            className="input"
            type="number"
            min={0}
            max={100}
            value={progress}
            onChange={(event) => setProgress(Number(event.target.value))}
          />
          <button
            className="button"
            type="button"
            disabled={savingProgress}
            onClick={handleSaveProgress}
          >
            {savingProgress ? "Salvando…" : "Salvar progresso"}
          </button>
        </div>
      </div>

      {CANCELLABLE_STATUSES.has(goal.status) && (
        <button
          className="button"
          type="button"
          disabled={cancelling}
          onClick={handleCancel}
          style={{ marginBottom: "1rem" }}
        >
          {cancelling ? "Cancelando…" : "Cancelar meta"}
        </button>
      )}

      <div style={{ marginBottom: "1rem" }}>
        <p>
          <strong>Dependências</strong>
        </p>
        {loadingDependencies && <p className="muted">Carregando…</p>}
        {!loadingDependencies && (!dependencies || dependencies.length === 0) && (
          <p className="muted">Nenhuma dependência.</p>
        )}
        {!loadingDependencies && dependencies && dependencies.length > 0 && (
          <ul>
            {dependencies.map((dep) => (
              <li key={dep.id}>
                {dep.title}
                <button
                  className="button"
                  type="button"
                  onClick={() => handleRemoveDependency(dep.id)}
                  style={{ marginLeft: "0.5rem" }}
                >
                  Remover
                </button>
              </li>
            ))}
          </ul>
        )}
        {candidateGoals.length > 0 && (
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
            <select
              className="input"
              aria-label="Nova dependência"
              value={dependsOnId}
              onChange={(event) => setDependsOnId(event.target.value)}
            >
              <option value="">Selecione uma meta…</option>
              {candidateGoals.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.title}
                </option>
              ))}
            </select>
            <button className="button" type="button" onClick={handleAddDependency}>
              Adicionar dependência
            </button>
          </div>
        )}
      </div>

      <div>
        <p>
          <strong>Histórico</strong>
        </p>
        {loadingHistory && <p className="muted">Carregando…</p>}
        {!loadingHistory && (!history || history.length === 0) && (
          <p className="muted">Nenhum evento registrado.</p>
        )}
        {!loadingHistory && history && history.length > 0 && (
          <ul>
            {history.map((entry) => (
              <li key={entry.id}>
                {entry.message} — {entry.created_at}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
