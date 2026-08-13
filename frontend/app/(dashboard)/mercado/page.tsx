"use client";

import PageHeader from "@/components/PageHeader";
import StatCard from "@/components/StatCard";
import { useApi } from "@/hooks/useApi";

interface Score {
  dimension: string;
  status: string;
  score: number | null;
  window_days: number;
  computed_at?: string;
  z_scores?: Record<string, number>;
  sample_counts?: Record<string, number>;
}

interface MarketEvent {
  id: string;
  timestamp: string;
  source: string;
  category: string;
  symbol: string;
  event: string;
  severity: string;
  confidence: number;
  payload: Record<string, unknown>;
}

const DIMENSION_LABELS: Record<string, string> = {
  commodities: "Commodities",
  liquidity: "Liquidez",
  risk: "Sentimento de risco",
};

const SYMBOL_LABELS: Record<string, string> = {
  "^TNX": "Treasury 10y",
  "USDBRL=X": "Dólar (USD/BRL)",
  "GC=F": "Ouro",
  "CL=F": "Petróleo (WTI)",
  "^VIX": "VIX",
};

function formatNumber(value: number, digits = 2): string {
  return value.toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatTimestamp(iso?: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("pt-BR");
  } catch {
    return iso;
  }
}

export default function MercadoPage() {
  const scoresApi = useApi<{ scores: Score[] }>("/mercado/scores");
  const eventsApi = useApi<{ events: MarketEvent[] }>("/mercado/events");
  const healthApi = useApi<{ backend: string; flowcore: boolean; flowcore_url: string }>(
    "/mercado/health"
  );

  return (
    <>
      <PageHeader
        title="Mercado"
        subtitle="Inteligência de mercado em tempo real — fornecida pelo FlowCore."
      />

      {healthApi.data && !healthApi.data.flowcore && (
        <p className="error">
          FlowCore indisponível em {healthApi.data.flowcore_url}. Os dados de
          mercado dependem do FlowCore estar rodando nesta máquina.
        </p>
      )}

      <h2 className="section-title">Scores macroeconômicos</h2>
      {scoresApi.loading && <p className="muted">Carregando scores…</p>}
      {scoresApi.error && <p className="error">Erro: {scoresApi.error}</p>}
      {scoresApi.data && (
        <div className="stat-grid">
          {scoresApi.data.scores.length === 0 && (
            <p className="muted">
              Nenhuma dimensão pontuada ainda. Os observadores de mercado
              precisam de algumas coletas antes de pontuar.
            </p>
          )}
          {scoresApi.data.scores.map((score) => (
            <div key={score.dimension} className="stat-card market-score-card">
              <div className="label">
                {DIMENSION_LABELS[score.dimension] ?? score.dimension}
              </div>
              <div className="value">
                {score.status === "scored" && score.score !== null
                  ? formatNumber(score.score)
                  : score.status ?? "—"}
              </div>
              {score.z_scores && (
                <div className="sub">
                  {Object.entries(score.z_scores).map(([symbol, z]) => (
                    <span key={symbol} className="z-tag">
                      {SYMBOL_LABELS[symbol] ?? symbol}: {formatNumber(z)}σ
                    </span>
                  ))}
                </div>
              )}
              <div className="meta">
                {score.sample_counts
                  ? Object.entries(score.sample_counts)
                      .map(([k, v]) => `${k}: ${v} amostras`)
                      .join(" · ")
                  : `janela ${score.window_days}d`}
              </div>
            </div>
          ))}
        </div>
      )}

      <h2 className="section-title">Eventos recentes</h2>
      {eventsApi.loading && <p className="muted">Carregando eventos…</p>}
      {eventsApi.error && <p className="error">Erro: {eventsApi.error}</p>}
      {eventsApi.data && (
        <div className="events-list">
          {eventsApi.data.events.length === 0 && (
            <p className="muted">
              Nenhum evento registrado ainda. Os observadores capturam
              movimentos de yield, câmbio e commodities continuamente.
            </p>
          )}
          {eventsApi.data.events.map((event) => (
            <div key={event.id} className="event-row">
              <div className="event-main">
                <span className="event-symbol">
                  {SYMBOL_LABELS[event.symbol] ?? event.symbol}
                </span>
                <span className="event-name">{event.event}</span>
              </div>
              <div className="event-meta">
                <span>{event.category}</span>
                <span>
                  {formatNumber(
                    (event.payload.value as number) ?? 0
                  )}
                </span>
                <span title={event.timestamp}>
                  {formatTimestamp(event.timestamp)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
