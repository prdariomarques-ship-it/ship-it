"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

import PageHeader from "@/components/PageHeader";
import { API_URL, getToken, setTokens } from "@/hooks/useApi";

function ChangePasswordForm() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(false);
    try {
      // Deliberately NOT using apiFetch() here: it treats any 401 on an
      // authenticated request as an expired session and redirects to
      // /login after one refresh+retry — correct for a stale token, wrong
      // for "current password doesn't match", which is also a 401 and
      // would otherwise bounce the user out mid-form instead of showing
      // the error inline.
      const response = await fetch(`${API_URL}/auth/change-password`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail ?? "Falha ao trocar a senha");
      }
      setSuccess(true);
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao trocar a senha");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <input
        className="input"
        type="password"
        placeholder="Senha atual"
        value={currentPassword}
        onChange={(event) => setCurrentPassword(event.target.value)}
        required
        style={{ marginBottom: "0.6rem" }}
      />
      <input
        className="input"
        type="password"
        placeholder="Nova senha (mínimo 8 caracteres)"
        value={newPassword}
        onChange={(event) => setNewPassword(event.target.value)}
        minLength={8}
        required
        style={{ marginBottom: "0.6rem" }}
      />
      {error && (
        <p className="error" style={{ marginBottom: "0.6rem" }}>
          {error}
        </p>
      )}
      {success && (
        <p className="muted" style={{ marginBottom: "0.6rem" }}>
          Senha trocada. Outras sessões abertas foram encerradas.
        </p>
      )}
      <button className="button" type="submit" disabled={submitting}>
        {submitting ? "Trocando…" : "Trocar senha"}
      </button>
    </form>
  );
}

export default function ConfiguracoesPage() {
  return (
    <>
      <PageHeader
        title="Configurações"
        subtitle="Sessão e informações da API. Preferências de providers e conexões (Google Workspace, WhatsApp) ficam em Admin."
      />
      <div className="card">
        <h3 style={{ marginBottom: "0.5rem" }}>Conexões</h3>
        <p className="muted">
          Google Workspace e WhatsApp são geridos na área administrativa, não aqui.
        </p>
        <p className="muted">
          <Link href="/admin/google">Google Workspace</Link> ·{" "}
          <Link href="/admin/whatsapp">WhatsApp</Link> ·{" "}
          <Link href="/admin/settings">Providers configurados</Link>
        </p>
      </div>
      <div className="card">
        <h3 style={{ marginBottom: "0.5rem" }}>API</h3>
        <p className="muted">
          Endpoint: <code>{API_URL}</code>
        </p>
        <p className="muted">
          Documentação OpenAPI disponível em <code>/docs</code> no backend.
        </p>
      </div>
      <div className="card">
        <h3 style={{ marginBottom: "0.5rem" }}>Trocar senha</h3>
        <ChangePasswordForm />
      </div>
      <div className="card">
        <h3 style={{ marginBottom: "0.5rem" }}>Sessão</h3>
        <button
          className="button"
          onClick={() => {
            setTokens(null, null);
            window.location.href = "/login";
          }}
        >
          Sair
        </button>
      </div>
    </>
  );
}
