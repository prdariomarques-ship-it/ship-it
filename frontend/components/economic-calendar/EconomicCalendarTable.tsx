"use client";

interface EconomicEvent {
  id: string;
  name: string;
  country_code: string;
  country_name: string;
  currency: string;
  date_utc: string;
  volatility: string;
  actual: string | null;
  forecast: string | null;
  previous: string | null;
  unit: string | null;
  category: string | null;
  impact: string | null;
  url: string | null;
}

const VOLATILITY_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  HIGH: { bg: "#dc354520", color: "#dc3545", label: "Alto" },
  MEDIUM: { bg: "#ffc10720", color: "#ffc107", label: "Médio" },
  LOW: { bg: "#28a74520", color: "#28a745", label: "Baixo" },
  NONE: { bg: "#6c757d20", color: "#6c757d", label: "—" },
};

function VolatilityBadge({ volatility }: { volatility: string }) {
  const style = VOLATILITY_STYLES[volatility] ?? VOLATILITY_STYLES.NONE;
  return (
    <span
      style={{
        display: "inline-block",
        padding: "0.15rem 0.55rem",
        borderRadius: "999px",
        fontSize: "0.75rem",
        fontWeight: 600,
        background: style.bg,
        color: style.color,
      }}
    >
      {style.label}
    </span>
  );
}

function formatEventDate(isoString: string): string {
  try {
    const date = new Date(isoString);
    return date.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

export default function EconomicCalendarTable({
  events,
}: {
  events: EconomicEvent[];
}) {
  if (events.length === 0) {
    return (
      <div className="card">
        <p className="muted" style={{ textAlign: "center", padding: "2rem" }}>
          Nenhum evento econômico encontrado para os filtros selecionados.
        </p>
      </div>
    );
  }

  return (
    <div className="card table-scroll">
      <table>
        <thead>
          <tr>
            <th>Data</th>
            <th>País</th>
            <th>Evento</th>
            <th>Impacto</th>
            <th>Anterior</th>
            <th>Previsão</th>
            <th>Atual</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.id}>
              <td style={{ whiteSpace: "nowrap" }}>
                {formatEventDate(event.date_utc)}
              </td>
              <td style={{ whiteSpace: "nowrap" }}>
                <span className="badge">{event.country_code}</span>
                {event.country_name && (
                  <span
                    className="muted"
                    style={{ marginLeft: "0.4rem", fontSize: "0.8rem" }}
                  >
                    {event.country_name}
                  </span>
                )}
              </td>
              <td>
                <strong>{event.name}</strong>
                {event.category && (
                  <span
                    className="muted"
                    style={{ marginLeft: "0.4rem", fontSize: "0.78rem" }}
                  >
                    {event.category}
                  </span>
                )}
              </td>
              <td>
                <VolatilityBadge volatility={event.volatility} />
              </td>
              <td className="muted">{event.previous ?? "—"}</td>
              <td className="muted">{event.forecast ?? "—"}</td>
              <td style={{ fontWeight: event.actual ? 600 : 400 }}>
                {event.actual ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
