"use client";

import { FormEvent, Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/hooks/useApi";

function RedefinirSenhaForm() {
  const searchParams = useSearchParams();
  const [token, setToken] = useState(() => searchParams.get("token") ?? "");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError("As senhas não coincidem");
      return;
    }
    setSubmitting(true);
    try {
      await apiFetch("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Token inválido ou expirado");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1 className="page-title" style={{ marginBottom: "1.25rem" }}>
          Redefinir senha
        </h1>

        {done ? (
          <p className="muted">
            Senha redefinida com sucesso. <Link href="/login">Entrar</Link>
          </p>
        ) : (
          <form onSubmit={handleSubmit}>
            <input
              className="input"
              placeholder="Token de redefinição"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              required
            />
            <input
              className="input"
              type="password"
              placeholder="Nova senha"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              minLength={8}
              required
            />
            <input
              className="input"
              type="password"
              placeholder="Confirmar nova senha"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              minLength={8}
              required
            />
            {error && (
              <p className="error" style={{ marginBottom: "0.9rem" }}>
                {error}
              </p>
            )}
            <button className="button" type="submit" disabled={submitting}>
              {submitting ? "Redefinindo…" : "Redefinir senha"}
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

export default function RedefinirSenhaPage() {
  return (
    <Suspense fallback={null}>
      <RedefinirSenhaForm />
    </Suspense>
  );
}
