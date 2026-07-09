"use client";

import PageHeader from "@/components/PageHeader";
import { API_URL, setTokens } from "@/hooks/useApi";

export default function ConfiguracoesPage() {
  return (
    <>
      <PageHeader
        title="Configurações"
        subtitle="Preferências e conexões do Dario OS."
      />
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
