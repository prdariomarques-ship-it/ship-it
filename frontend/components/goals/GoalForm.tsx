"use client";

import { FormEvent, useState } from "react";

import { apiFetch } from "@/hooks/useApi";

const PRIORITY_OPTIONS = [
  { value: "low", label: "Baixa" },
  { value: "medium", label: "Média" },
  { value: "high", label: "Alta" },
  { value: "urgent", label: "Urgente" },
];

export default function GoalForm({ onCreated }: { onCreated: () => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("medium");
  const [deadline, setDeadline] = useState("");
  const [recurrenceDays, setRecurrenceDays] = useState("");
  const [requiresApproval, setRequiresApproval] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setTitle("");
    setDescription("");
    setPriority("medium");
    setDeadline("");
    setRecurrenceDays("");
    setRequiresApproval(false);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch("/goals", {
        method: "POST",
        body: JSON.stringify({
          title,
          description: description || null,
          priority,
          deadline: deadline ? new Date(deadline).toISOString() : null,
          recurrence_interval_days: recurrenceDays ? Number(recurrenceDays) : null,
          requires_approval: requiresApproval,
        }),
      });
      reset();
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar meta");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card" onSubmit={handleSubmit} aria-label="Nova meta">
      <input
        className="input"
        placeholder="Título da meta"
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        required
      />
      <textarea
        className="input"
        placeholder="Descrição (opcional)"
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        rows={2}
      />
      <select
        className="input"
        aria-label="Prioridade"
        value={priority}
        onChange={(event) => setPriority(event.target.value)}
      >
        {PRIORITY_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <input
        className="input"
        type="date"
        aria-label="Prazo"
        value={deadline}
        onChange={(event) => setDeadline(event.target.value)}
      />
      <input
        className="input"
        type="number"
        min={1}
        placeholder="Repetir a cada N dias (opcional)"
        value={recurrenceDays}
        onChange={(event) => setRecurrenceDays(event.target.value)}
      />
      <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.9rem" }}>
        <input
          type="checkbox"
          checked={requiresApproval}
          onChange={(event) => setRequiresApproval(event.target.checked)}
        />
        Exigir aprovação de um admin antes de começar
      </label>
      {error && <p className="error">{error}</p>}
      <button className="button" type="submit" disabled={submitting}>
        {submitting ? "Criando…" : "Criar meta"}
      </button>
    </form>
  );
}
