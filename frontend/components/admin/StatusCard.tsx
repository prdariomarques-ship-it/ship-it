import { CheckCircle2, XCircle } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { formatRelativeTime } from "@/lib/format";
import type { ComponentStatus } from "@/lib/admin-types";

const DISPLAY_NAME: Record<string, string> = {
  backend: "Backend",
  database: "Database",
  redis: "Redis",
  qdrant: "Qdrant",
  whatsapp: "WhatsApp",
  memory: "Memory",
  event_bus: "Event Bus",
  google_oauth: "Google OAuth",
  frontend: "Frontend",
};

export function StatusCard({ status }: { status: ComponentStatus }) {
  const label = DISPLAY_NAME[status.name] ?? status.name;

  return (
    <Card className={status.online ? "" : "border-destructive/40"}>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle>{label}</CardTitle>
        {status.online ? (
          <CheckCircle2 className="h-4 w-4 text-success" />
        ) : (
          <XCircle className="h-4 w-4 text-destructive" />
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-1">
        <span className={"text-sm font-medium " + (status.online ? "text-success" : "text-destructive")}>
          {status.online ? "Online" : "Offline"}
        </span>
        <span className="text-xs text-muted-foreground">
          {status.latency_ms !== null ? `${status.latency_ms.toFixed(1)}ms · ` : ""}
          heartbeat {formatRelativeTime(status.last_heartbeat)}
        </span>
        {status.detail ? <span className="truncate text-xs text-muted-foreground">{status.detail}</span> : null}
      </CardContent>
    </Card>
  );
}
