"use client";

import { useEffect, useState } from "react";
import { drtApi, type DRTHealth } from "@/lib/drt-api";
import { AdminPageHeader } from "@/components/admin/PageHeader";
import { StatusCard } from "@/components/admin/StatusCard";
import { MetricCard } from "@/components/admin/MetricCard";
import { ErrorState } from "@/components/admin/ErrorState";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { Server, AlertCircle, CheckCircle, Clock } from "lucide-react";

export default function RuntimeOverviewPage() {
  const [health, setHealth] = useState<DRTHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadHealth = async () => {
      try {
        setLoading(true);
        const data = await drtApi.getHealth();
        setHealth(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load Runtime health");
      } finally {
        setLoading(false);
      }
    };

    loadHealth();
    const interval = setInterval(loadHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <AdminPageHeader
        title="DRT Runtime"
        subtitle="Deterministic Resilient Transactions Runtime v1.0.0-LTS"
      />

      {error && (
        <ErrorState
          message={error}
          onRetry={() => {
            setError(null);
            setLoading(true);
          }}
        />
      )}

      {loading ? (
        <LoadingGrid count={4} />
      ) : health ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatusCard
              status={{
                name: "Runtime Status",
                online: health.status === "healthy",
                detail: health.status,
                latency_ms: 0,
                last_heartbeat: new Date().toISOString(),
              }}
            />
            <MetricCard label="Version" value={health.version || "1.0.0"} icon={Server} />
            <MetricCard
              label="Uptime"
              value={formatUptime(health.uptime_seconds || 0)}
              icon={Clock}
            />
            <MetricCard
              label="Active Executions"
              value={String(health.active_executions || 0)}
              icon={AlertCircle}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-border bg-card p-6">
              <h3 className="mb-4 font-semibold">Storage Status</h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Storage Valid</span>
                  <span className="flex items-center gap-2">
                    {health.storage_valid ? (
                      <>
                        <CheckCircle className="h-4 w-4 text-green-600" />
                        <span className="text-sm font-medium text-green-600">OK</span>
                      </>
                    ) : (
                      <>
                        <AlertCircle className="h-4 w-4 text-red-600" />
                        <span className="text-sm font-medium text-red-600">Error</span>
                      </>
                    )}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Accepting Requests</span>
                  <span className="flex items-center gap-2">
                    {health.accepting_requests ? (
                      <>
                        <CheckCircle className="h-4 w-4 text-green-600" />
                        <span className="text-sm font-medium text-green-600">OK</span>
                      </>
                    ) : (
                      <>
                        <AlertCircle className="h-4 w-4 text-red-600" />
                        <span className="text-sm font-medium text-red-600">Error</span>
                      </>
                    )}
                  </span>
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-border bg-card p-6">
              <h3 className="mb-4 font-semibold">Configuration</h3>
              <div className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Mode</span>
                  <span className="font-medium">File-based + WAL</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Durability</span>
                  <span className="font-medium">fsync()</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">LTS Period</span>
                  <span className="font-medium">18 months</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Crash Safe</span>
                  <span className="font-medium text-green-600">Yes</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function formatUptime(seconds: number): string {
  if (!seconds) return "0s";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}
