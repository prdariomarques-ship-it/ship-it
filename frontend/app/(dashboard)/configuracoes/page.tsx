"use client";

import Link from "next/link";

import PageHeader from "@/components/PageHeader";
import { API_URL, setTokens } from "@/hooks/useApi";

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
