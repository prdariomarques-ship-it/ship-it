"use client";

import { useEffect, useState } from "react";
import { AdminPageHeader } from "@/components/admin/PageHeader";
import { EmptyState } from "@/components/admin/EmptyState";
import { ErrorState } from "@/components/admin/ErrorState";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { MetricCard } from "@/components/admin/MetricCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Badge } from "@/components/admin/ui/badge";
import { CheckCircle, AlertCircle, Zap, Clock } from "lucide-react";

interface RecoveryEvent {
  timestamp: string;
  event_type: string;
  status: "success" | "failed" | "in_progress";
  duration_ms: number;
  details?: string;
}

export default function RuntimeRecoveryPage() {
  const [recoveryEvents, setRecoveryEvents] = useState<RecoveryEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [recoveryStats, setRecoveryStats] = useState({
    totalRecoveries: 0,
    successfulRecoveries: 0,
    failedRecoveries: 0,
    averageRecoveryTime: 0,
  });

  useEffect(() => {
    const loadRecoveryData = async () => {
      try {
        setLoading(true);
        setError(null);
        // In a real implementation, this would call an endpoint to fetch recovery data
        // For now, we show empty state as the endpoint needs to be implemented
        setRecoveryEvents([]);
        setRecoveryStats({
          totalRecoveries: 0,
          successfulRecoveries: 0,
          failedRecoveries: 0,
          averageRecoveryTime: 0,
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load recovery data");
      } finally {
        setLoading(false);
      }
    };

    loadRecoveryData();
    const interval = setInterval(loadRecoveryData, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <AdminPageHeader
        title="Recovery Management"
        subtitle="Track crash recovery, WAL replay, and system resilience"
      />

      {error && <ErrorState message={error} onRetry={() => window.location.reload()} />}

      {loading ? (
        <LoadingGrid count={4} />
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="Total Recoveries"
              value={recoveryStats.totalRecoveries}
              icon={Zap}
            />
            <MetricCard
              label="Successful"
              value={recoveryStats.successfulRecoveries}
              icon={CheckCircle}
              tone="success"
            />
            <MetricCard
              label="Failed"
              value={recoveryStats.failedRecoveries}
              icon={AlertCircle}
              tone={recoveryStats.failedRecoveries > 0 ? "destructive" : "default"}
            />
            <MetricCard
              label="Avg Recovery Time"
              value={`${recoveryStats.averageRecoveryTime}ms`}
              icon={Clock}
            />
          </div>

          <div className="rounded-lg border border-border bg-card p-6">
            <h3 className="mb-4 font-semibold">Recovery Capabilities</h3>
            <div className="space-y-3">
              <RecoveryCapability
                label="Crash Recovery"
                status="enabled"
                description="Automatic recovery from system crashes via WAL replay"
              />
              <RecoveryCapability
                label="Write-Ahead Logging"
                status="enabled"
                description="All transactions logged before execution"
              />
              <RecoveryCapability
                label="Checkpoint Mechanism"
                status="enabled"
                description="Periodic state snapshots for faster recovery"
              />
              <RecoveryCapability
                label="Idempotent Replay"
                status="enabled"
                description="Safe re-execution of persisted operations"
              />
            </div>
          </div>

          {recoveryEvents.length === 0 ? (
            <EmptyState
              title="No recovery events yet"
              description="Recovery events will appear here when they occur"
            />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Recovery Event History</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {recoveryEvents.map((event, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between rounded-lg border border-border p-3"
                    >
                      <div>
                        <p className="font-medium text-sm">{event.event_type}</p>
                        <p className="text-xs text-muted-foreground">{event.timestamp}</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-muted-foreground">{event.duration_ms}ms</span>
                        <Badge
                          variant={
                            event.status === "success"
                              ? "success"
                              : event.status === "failed"
                              ? "destructive"
                              : "secondary"
                          }
                        >
                          {event.status}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

function RecoveryCapability({
  label,
  status,
  description,
}: {
  label: string;
  status: string;
  description: string;
}) {
  return (
    <div className="flex items-start justify-between border-t border-border pt-3 first:border-t-0 first:pt-0">
      <div>
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <Badge variant="success">{status}</Badge>
    </div>
  );
}
