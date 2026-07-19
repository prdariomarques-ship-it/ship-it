"use client";

import { FormEvent, useState } from "react";

import { apiFetch } from "@/hooks/useApi";

export default function CalendarEventForm({ onCreated }: { onCreated: () => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [location, setLocation] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setTitle("");
    setDescription("");
    setLocation("");
    setStartsAt("");
    setEndsAt("");
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch("/calendar", {
        method: "POST",
        body: JSON.stringify({
          title,
          description: description || null,
          location: location || null,
          starts_at: new Date(startsAt).toISOString(),
          ends_at: endsAt ? new Date(endsAt).toISOString() : null,
        }),
      });
      reset();
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar evento");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card" onSubmit={handleSubmit} aria-label="Novo evento">
      <input
        className="input"
        placeholder="Título do evento"
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
      <input
        className="input"
        placeholder="Local (opcional)"
        value={location}
        onChange={(event) => setLocation(event.target.value)}
      />
      <label className="muted" style={{ display: "block", marginBottom: "0.25rem" }}>
        Início
      </label>
      <input
        className="input"
        type="datetime-local"
        aria-label="Início"
        value={startsAt}
        onChange={(event) => setStartsAt(event.target.value)}
        required
      />
      <label className="muted" style={{ display: "block", marginBottom: "0.25rem" }}>
        Fim (opcional)
      </label>
      <input
        className="input"
        type="datetime-local"
        aria-label="Fim"
        value={endsAt}
        onChange={(event) => setEndsAt(event.target.value)}
      />
      {error && <p className="error">{error}</p>}
      <button className="button" type="submit" disabled={submitting}>
        {submitting ? "Criando…" : "Criar evento"}
      </button>
    </form>
  );
}
