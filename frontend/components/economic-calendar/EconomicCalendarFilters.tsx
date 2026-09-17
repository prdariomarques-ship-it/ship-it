"use client";

interface CountryInfo {
  code: string;
  name: string;
}

const VOLATILITY_OPTIONS = [
  { value: "", label: "Todos" },
  { value: "HIGH", label: "Alto impacto" },
  { value: "MEDIUM", label: "Médio impacto" },
  { value: "LOW", label: "Baixo impacto" },
  { value: "NONE", label: "Sem impacto" },
];

interface FiltersProps {
  countries: CountryInfo[];
  selectedCountry: string;
  selectedVolatility: string;
  onCountryChange: (value: string) => void;
  onVolatilityChange: (value: string) => void;
  onRefresh: () => void;
  loading: boolean;
}

export default function EconomicCalendarFilters({
  countries,
  selectedCountry,
  selectedVolatility,
  onCountryChange,
  onVolatilityChange,
  onRefresh,
  loading,
}: FiltersProps) {
  const selectStyle: React.CSSProperties = {
    background: "var(--bg)",
    border: "1px solid var(--border)",
    borderRadius: "8px",
    padding: "0.5rem 0.8rem",
    color: "var(--text)",
    font: "inherit",
    cursor: "pointer",
  };

  return (
    <div
      className="card"
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "0.75rem",
        alignItems: "center",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
          País
        </label>
        <select
          value={selectedCountry}
          onChange={(e) => onCountryChange(e.target.value)}
          style={selectStyle}
        >
          <option value="">Todos os países</option>
          {countries.map((c) => (
            <option key={c.code} value={c.code}>
              {c.code} — {c.name}
            </option>
          ))}
        </select>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
          Impacto
        </label>
        <select
          value={selectedVolatility}
          onChange={(e) => onVolatilityChange(e.target.value)}
          style={selectStyle}
        >
          {VOLATILITY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <button
        className="button"
        type="button"
        onClick={onRefresh}
        disabled={loading}
        style={{ marginTop: "1.1rem", opacity: loading ? 0.6 : 1 }}
      >
        {loading ? "Carregando…" : "Atualizar"}
      </button>
    </div>
  );
}
