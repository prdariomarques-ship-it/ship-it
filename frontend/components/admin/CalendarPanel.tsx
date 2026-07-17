import { MapPin } from "lucide-react";

import { EmptyState } from "@/components/admin/EmptyState";
import { formatDateTime } from "@/lib/format";
import type { CalendarEventRead } from "@/lib/admin-types";

export function CalendarPanel({ events }: { events: CalendarEventRead[] }) {
  if (events.length === 0) {
    return <EmptyState title="Nenhum evento próximo" description="Sem eventos futuros na agenda." />;
  }

  return (
    <ul className="flex flex-col gap-2">
      {events.map((event) => (
        <li key={event.id} className="rounded-md border border-border bg-card p-3">
          <span className="text-sm font-medium">{event.title}</span>
          <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(event.starts_at)}</p>
          {event.location ? (
            <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
              <MapPin className="h-3 w-3" /> {event.location}
            </p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
