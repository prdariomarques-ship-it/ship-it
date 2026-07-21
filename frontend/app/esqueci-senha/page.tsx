"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/hooks/useApi";

export default function EsqueciSenhaPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao solicitar redefinição");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1 className="page-title" style={{ marginBottom: "1.25rem" }}>
          Esqueci minha senha
        </h1>

        {submitted ? (
          <p className="muted">
            Se esse e-mail tiver uma conta, sua solicitação foi registrada. Peça
            para um administrador gerar um token de redefinição para você e
            repassá-lo, e depois continue em{" "}
            <Link href="/redefinir-senha">Redefinir senha</Link>.
          </p>
        ) : (
          <form onSubmit={handleSubmit}>
            <input
              className="input"
              type="email"
              placeholder="E-mail"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
            {error && (
              <p className="error" style={{ marginBottom: "0.9rem" }}>
                {error}
              </p>
            )}
            <button className="button" type="submit" disabled={submitting}>
              {submitting ? "Enviando…" : "Solicitar redefinição"}
            </button>
          </form>
        )}

        <Link href="/login" className="muted" style={{ display: "block", marginTop: "0.9rem", textAlign: "center" }}>
          Voltar ao login
        </Link>
      </div>
    </div>
  );
}
