"use client";

import { FormEvent, useState } from "react";

import { apiFetch } from "@/hooks/useApi";

const PRIORITY_OPTIONS = [
  { value: "low", label: "Baixa" },
  { value: "medium", label: "Média" },
  { value: "high", label: "Alta" },
];

export default function TaskForm({ onCreated }: { onCreated: () => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("medium");
  const [dueDate, setDueDate] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setTitle("");
    setDescription("");
    setPriority("medium");
    setDueDate("");
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch("/tasks", {
        method: "POST",
        body: JSON.stringify({
          title,
          description: description || null,
          priority,
          due_date: dueDate ? new Date(dueDate).toISOString() : null,
        }),
      });
      reset();
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar tarefa");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card" onSubmit={handleSubmit} aria-label="Nova tarefa">
      <input
        className="input"
        placeholder="Título da tarefa"
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
        value={dueDate}
        onChange={(event) => setDueDate(event.target.value)}
      />
      {error && <p className="error">{error}</p>}
      <button className="button" type="submit" disabled={submitting}>
        {submitting ? "Criando…" : "Criar tarefa"}
      </button>
    </form>
  );
}
