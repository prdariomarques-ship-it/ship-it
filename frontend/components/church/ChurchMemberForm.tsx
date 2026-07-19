"use client";

import { FormEvent, useState } from "react";

import { apiFetch } from "@/hooks/useApi";

export default function ChurchMemberForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [role, setRole] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setName("");
    setPhone("");
    setRole("");
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch("/church/members", {
        method: "POST",
        body: JSON.stringify({
          name,
          phone: phone || null,
          role: role || null,
        }),
      });
      reset();
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar membro");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card" onSubmit={handleSubmit} aria-label="Novo membro">
      <input
        className="input"
        placeholder="Nome"
        value={name}
        onChange={(event) => setName(event.target.value)}
        required
      />
      <input
        className="input"
        placeholder="Telefone (opcional)"
        value={phone}
        onChange={(event) => setPhone(event.target.value)}
      />
      <input
        className="input"
        placeholder="Função no ministério (opcional)"
        value={role}
        onChange={(event) => setRole(event.target.value)}
      />
      {error && <p className="error">{error}</p>}
      <button className="button" type="submit" disabled={submitting}>
        {submitting ? "Criando…" : "Criar membro"}
      </button>
    </form>
  );
}
