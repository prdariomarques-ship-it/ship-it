"use client";

import { FormEvent, useState } from "react";
import { apiFetch, setToken } from "@/hooks/useApi";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await apiFetch<{ access_token: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setToken(response.access_token);
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha no login");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1 className="page-title" style={{ marginBottom: "1.25rem" }}>
          Dario OS
        </h1>
        <input
          className="input"
          type="email"
          placeholder="E-mail"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <input
          className="input"
          type="password"
          placeholder="Senha"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
        {error && (
          <p className="error" style={{ marginBottom: "0.9rem" }}>
            {error}
          </p>
        )}
        <button className="button" type="submit" disabled={submitting}>
          {submitting ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </div>
  );
}
