"use client";
import { useCallback, useEffect, useState } from "react";
import PageHeader from "@/components/PageHeader";
import EconomicCalendarTable from "@/components/economic-calendar/EconomicCalendarTable";
import EconomicCalendarFilters from "@/components/economic-calendar/EconomicCalendarFilters";
import { apiFetch } from "@/hooks/useApi";

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

interface CountryInfo {
  code: string;
  name: string;
}

interface EventsResponse {
  events: EconomicEvent[];
  total: number;
  from_date: string | null;
  to_date: string | null;
  country_filter: string | null;
  volatility_filter: string | null;
}

interface CountriesResponse {
  countries: CountryInfo[];
  total: number;
}

export default function EconomicCalendarPage() {
  const [events, setEvents] = useState<EconomicEvent[]>([]);
  const [countries, setCountries] = useState<CountryInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingCountries, setLoadingCountries] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCountry, setSelectedCountry] = useState("");
  const [selectedVolatility, setSelectedVolatility] = useState("");
  const [version, setVersion] = useState(0);

  // Fetch countries on mount
  useEffect(() => {
    let active = true;
    async function fetchCountries() {
      try {
        const result = await apiFetch<CountriesResponse>(
          "/economic-calendar/countries"
        );
        if (active) {
          setCountries(result.countries);
          setLoadingCountries(false);
        }
      } catch (err) {
        if (active) {
          setLoadingCountries(false);
          // Non-critical: filters still work without country list
          console.error("Failed to load countries:", err);
        }
      }
    }
    fetchCountries();
    return () => {
      active = false;
    };
  }, []);

  // Build query params
  const buildQuery = useCallback(() => {
    const params = new URLSearchParams();
    if (selectedCountry) params.set("country_code", selectedCountry);
    if (selectedVolatility) params.set("volatility", selectedVolatility);
    params.set("limit", "100");
    return params.toString();
  }, [selectedCountry, selectedVolatility]);

  // Fetch events
  useEffect(() => {
    let active = true;
    async function fetchEvents() {
      setLoading(true);
      setError(null);
      try {
        const query = buildQuery();
        const path = `/economic-calendar/events?${query}`;
        const result = await apiFetch<EventsResponse>(path);
        if (active) {
          setEvents(result.events);
          setLoading(false);
        }
      } catch (err) {
        if (active) {
          setError((err as Error).message);
          setLoading(false);
        }
      }
    }
    fetchEvents();
    return () => {
      active = false;
    };
  }, [buildQuery, version]);

  const handleRefresh = useCallback(() => {
    setVersion((v) => v + 1);
  }, []);

  return (
    <>
      <PageHeader
        title="Calendário Econômico"
        subtitle="Eventos macroeconômicos globais: PIB, inflação, emprego e decisões de bancos centrais."
      />

      <EconomicCalendarFilters
        countries={countries}
        selectedCountry={selectedCountry}
        selectedVolatility={selectedVolatility}
        onCountryChange={setSelectedCountry}
        onVolatilityChange={setSelectedVolatility}
        onRefresh={handleRefresh}
        loading={loading}
      />

      {loading && (
        <p className="muted" style={{ textAlign: "center", padding: "2rem" }}>
          Carregando eventos econômicos…
        </p>
      )}

      {error && <p className="error">Erro: {error}</p>}

      {!loading && !error && (
        <>
          <div style={{ marginBottom: "0.75rem" }}>
            <span className="muted" style={{ fontSize: "0.85rem" }}>
              {events.length} evento{events.length !== 1 ? "s" : ""} encontrado
              {events.length !== 1 ? "s" : ""}
            </span>
          </div>
          <EconomicCalendarTable events={events} />
        </>
      )}
    </>
  );
}
