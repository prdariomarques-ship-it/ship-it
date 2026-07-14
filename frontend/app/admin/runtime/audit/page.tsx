"use client";

import { useEffect, useState } from "react";
import { AdminPageHeader } from "@/components/admin/PageHeader";
import { EmptyState } from "@/components/admin/EmptyState";
import { ErrorState } from "@/components/admin/ErrorState";
import { LoadingRows } from "@/components/admin/LoadingGrid";
import { Input } from "@/components/admin/ui/input";
import { Search, AlertCircle, CheckCircle, RefreshCw } from "lucide-react";
import { Card, CardContent } from "@/components/admin/ui/card";
import { Badge } from "@/components/admin/ui/badge";
import { formatDateTime } from "@/lib/format";

interface AuditEvent {
  timestamp: string;
  event: string;
  severity: "info" | "warning" | "error";
  details?: Record<string, any>;
  execution_id?: string;
}

export default function RuntimeAuditPage() {
  const [search, setSearch] = useState("");
  const [eventType, setEventType] = useState("all");
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadEvents = async () => {
      try {
        setLoading(true);
        setError(null);
        // In a real implementation, this would fetch from the DRT Runtime audit API
        // For now, we show empty state as the endpoint needs to be implemented
        setAuditEvents([]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load audit events");
      } finally {
        setLoading(false);
      }
    };

    loadEvents();
    const interval = setInterval(loadEvents, 5000);
    return () => clearInterval(interval);
  }, []);

  const filteredEvents = auditEvents.filter((event) => {
    const matchesSearch =
      event.event.toLowerCase().includes(search.toLowerCase()) ||
      event.execution_id?.toLowerCase().includes(search.toLowerCase());

    const matchesType =
      eventType === "all" ||
      (eventType === "state-transitions" && event.event.includes("state")) ||
      (eventType === "recovery" && event.event.includes("recovery")) ||
      (eventType === "errors" && event.severity === "error");

    return matchesSearch && matchesType;
  });

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case "error":
        return <AlertCircle className="h-4 w-4 text-red-600" />;
      case "warning":
        return <AlertCircle className="h-4 w-4 text-yellow-600" />;
      default:
        return <CheckCircle className="h-4 w-4 text-green-600" />;
    }
  };

  return (
    <div>
      <AdminPageHeader
        title="Audit Trail"
        subtitle="Chronological view of state transitions, recovery events, and errors"
      />

      <div className="mb-6 flex flex-col gap-4 md:flex-row">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search events or execution ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
            aria-label="Search audit events"
          />
        </div>
        <select
          value={eventType}
          onChange={(e) => setEventType(e.target.value)}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm"
          aria-label="Filter by event type"
        >
          <option value="all">All Events</option>
          <option value="state-transitions">State Transitions</option>
          <option value="recovery">Recovery Events</option>
          <option value="errors">Errors</option>
        </select>
      </div>

      <Card>
        <CardContent className="pt-4">
          {loading ? (
            <LoadingRows count={5} />
          ) : error ? (
            <ErrorState message={error} onRetry={() => window.location.reload()} />
          ) : filteredEvents.length === 0 ? (
            <EmptyState
              title="No audit events yet"
              description="Audit trail will show state transitions, recoveries, and errors as they occur"
            />
          ) : (
            <div className="space-y-3">
              {filteredEvents.map((event, index) => (
                <div
                  key={index}
                  className="flex items-start gap-3 rounded-lg border border-border p-3 hover:bg-accent/50 transition-colors"
                >
                  <div className="mt-0.5">{getSeverityIcon(event.severity)}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <p className="font-medium text-sm">{event.event}</p>
                      <Badge variant={event.severity === "error" ? "destructive" : "secondary"}>
                        {event.severity}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mb-1">
                      {formatDateTime(event.timestamp)}
                    </p>
                    {event.execution_id && (
                      <p className="text-xs font-mono text-muted-foreground">
                        Execution: {event.execution_id}
                      </p>
                    )}
                    {event.details && Object.keys(event.details).length > 0 && (
                      <details className="mt-2">
                        <summary className="text-xs cursor-pointer text-muted-foreground hover:text-foreground">
                          Details
                        </summary>
                        <pre className="mt-2 text-xs bg-background border border-border rounded p-2 overflow-auto max-h-32">
                          {JSON.stringify(event.details, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
