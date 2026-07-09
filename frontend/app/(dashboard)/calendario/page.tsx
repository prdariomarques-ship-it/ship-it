"use client";

import PageHeader from "@/components/PageHeader";
import { useApi } from "@/hooks/useApi";

interface CalendarEvent {
  id: number;
  title: string;
  location: string | null;
  starts_at: string;
  ends_at: string | null;
}

function groupByDay(events: CalendarEvent[]): Map<string, CalendarEvent[]> {
  const groups = new Map<string, CalendarEvent[]>();
  for (const event of events) {
    const day = new Date(event.starts_at).toLocaleDateString("pt-BR", {
      weekday: "long",
      day: "2-digit",
      month: "long",
      year: "numeric",
    });
    const bucket = groups.get(day) ?? [];
    bucket.push(event);
    groups.set(day, bucket);
  }
  return groups;
}

export default function CalendarioPage() {
  const { data, loading, error } = useApi<CalendarEvent[]>("/calendar?limit=100");

  const sorted = (data ?? [])
    .slice()
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  const groups = groupByDay(sorted);

  return (
    <>
      <PageHeader
        title="Calendário"
        subtitle="Seus eventos organizados por dia."
      />
      {loading && <p className="muted">Carregando…</p>}
      {error && <p className="error">Erro: {error}</p>}
      {!loading && !error && groups.size === 0 && (
        <p className="muted">Nenhum evento no calendário.</p>
      )}
      {Array.from(groups.entries()).map(([day, events]) => (
        <div className="card" key={day}>
          <h3 style={{ marginBottom: "0.75rem", textTransform: "capitalize" }}>
            {day}
          </h3>
          <table>
            <tbody>
              {events.map((event) => (
                <tr key={event.id}>
                  <td style={{ whiteSpace: "nowrap", width: "6rem" }}>
                    {new Date(event.starts_at).toLocaleTimeString("pt-BR", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </td>
                  <td>{event.title}</td>
                  <td className="muted">{event.location ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </>
  );
}
