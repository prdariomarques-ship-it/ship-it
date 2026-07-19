"use client";

import { FormEvent, useState } from "react";

import { apiFetch } from "@/hooks/useApi";

export default function StoreCustomerForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setName("");
    setPhone("");
    setEmail("");
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch("/store/customers", {
        method: "POST",
        body: JSON.stringify({
          name,
          phone: phone || null,
          email: email || null,
        }),
      });
      reset();
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar cliente");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card" onSubmit={handleSubmit} aria-label="Novo cliente">
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
        type="email"
        placeholder="E-mail (opcional)"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
      />
      {error && <p className="error">{error}</p>}
      <button className="button" type="submit" disabled={submitting}>
        {submitting ? "Criando…" : "Criar cliente"}
      </button>
    </form>
  );
}
