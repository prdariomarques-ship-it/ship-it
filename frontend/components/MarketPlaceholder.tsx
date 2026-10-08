import PageHeader from "@/components/PageHeader";

// Mercado · Brasil e Mercado Global são áreas novas na navegação aprovada
// (DESIGN.md) sem fonte de dados conectada ainda — mostram estado
// explícito de indisponibilidade, nunca um número ou notícia inventados.
// Quando uma fonte real existir, esta página troca para useApi/apiFetch
// como qualquer outra do app; até lá, nada aqui chama a API.
export default function MarketPlaceholder({ scope }: { scope: "brasil" | "global" }) {
  const title = scope === "brasil" ? "Mercado · Brasil" : "Mercado Global";
  const subtitle =
    scope === "brasil"
      ? "Índices, agenda macro e notícias locais, numa área própria para o Brasil."
      : "EUA, Europa e demais mercados, separados do contexto brasileiro.";

  return (
    <>
      <PageHeader title={title} subtitle={subtitle} />
      <div className="card">
        <h2 className="page-title" style={{ fontSize: "1rem" }}>
          Estado da fonte
        </h2>
        <p className="muted" style={{ marginBottom: "0.75rem" }}>
          Nenhuma fonte de mercado está conectada a esta área ainda.
        </p>
        <div className="empty-state">
          <span className="badge badge-stale" style={{ flexShrink: 0 }}>
            Sem dado ao vivo
          </span>
          <div>
            <strong>Aguardando uma fonte autorizada</strong>
            Quando uma fonte for conectada, esta página mostra cotação, agenda e
            notícias com origem e horário de atualização — nunca um valor
            aproximado ou de exemplo.
          </div>
        </div>
      </div>
    </>
  );
}
