import { Bot, Server, User } from "lucide-react";

import { Badge } from "@/components/admin/ui/badge";
import { formatDateTime } from "@/lib/format";
import type { Actor, TimelineEvent } from "@/lib/timeline";

const ACTOR_ICON: Record<Actor, React.ElementType> = {
  user: User,
  ai: Bot,
  system: Server,
};

const ACTOR_LABEL: Record<Actor, string> = {
  user: "você",
  ai: "IA",
  system: "sistema",
};

function importanceTone(importance: number): "destructive" | "warning" | "secondary" {
  if (importance >= 75) return "destructive";
  if (importance >= 45) return "warning";
  return "secondary";
}

export function TimelineEventCard({ event }: { event: TimelineEvent }) {
  const ActorIcon = ACTOR_ICON[event.actor];
  return (
    <li className="rounded-md border border-border bg-card p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <ActorIcon className="h-3.5 w-3.5" />
          {ACTOR_LABEL[event.actor]}
        </span>
        <span className="text-sm font-medium">{event.summary}</span>
        <Badge variant={importanceTone(event.importance)}>{event.importance}</Badge>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Por quê: </span>
        {event.reason}
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Consequência: </span>
        {event.consequence}
      </p>
      {event.relatedEntities.length > 0 ? (
        <p className="mt-0.5 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Relacionado: </span>
          {event.relatedEntities.join(", ")}
        </p>
      ) : null}
      {event.suggestedFollowUp ? (
        <p className="mt-0.5 text-xs text-primary">
          <span className="font-medium">Sugestão: </span>
          {event.suggestedFollowUp}
        </p>
      ) : null}
      <p className="mt-1 text-[11px] text-muted-foreground">{formatDateTime(event.timestamp)}</p>
    </li>
  );
}
