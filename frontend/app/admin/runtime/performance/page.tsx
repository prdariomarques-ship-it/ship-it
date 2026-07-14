"use client";

import { useEffect, useState } from "react";
import { drtApi, type DRTHealth, type DRTExecution } from "@/lib/drt-api";
import { AdminPageHeader } from "@/components/admin/PageHeader";
import { ErrorState } from "@/components/admin/ErrorState";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { MetricCard } from "@/components/admin/MetricCard";
import { Zap, Clock, Activity, TrendingUp } from "lucide-react";

export default function RuntimePerformancePage() {
  const [health, setHealth] = useState<DRTHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState({
    executionsCompleted: 0,
    executionsFailed: 0,
    executionsRecovered: 0,
    averageLatency: 0,
  });

  useEffect(() => {
    const loadData = async () => {
      try {
        const data = await drtApi.getHealth();
        setHealth(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load performance data");
      } finally {
        setLoading(false);
      }
    };

    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <AdminPageHeader
        title="Performance"
        subtitle="Runtime metrics, throughput, and latency monitoring"
      />

      {error && (
        <ErrorState message={error} onRetry={() => setLoading(true)} />
      )}

      {loading ? (
        <LoadingGrid count={4} />
      ) : health ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="System Status"
              value={health.status === "healthy" ? "Healthy" : "Degraded"}
              icon={Activity}
              tone={health.status === "healthy" ? "success" : "warning"}
            />
            <MetricCard
              label="API Responsive"
              value={health.accepting_requests ? "Yes" : "No"}
              icon={Zap}
              tone={health.accepting_requests ? "success" : "destructive"}
            />
            <MetricCard
              label="Version"
              value={health.version || "1.0.0"}
              icon={TrendingUp}
            />
            <MetricCard
              label="Uptime"
              value="Active"
              icon={Clock}
              tone="success"
            />
          </div>

          <div className="rounded-lg border border-border bg-card p-6">
            <h3 className="mb-4 font-semibold">Execution Metrics</h3>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <div className="space-y-1">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Completed
                </p>
                <p className="text-2xl font-semibold">{stats.executionsCompleted}</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Failed
                </p>
                <p className="text-2xl font-semibold text-red-600">{stats.executionsFailed}</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Recovered
                </p>
                <p className="text-2xl font-semibold text-blue-600">{stats.executionsRecovered}</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Avg Latency
                </p>
                <p className="text-2xl font-semibold">{stats.averageLatency}ms</p>
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-border bg-card p-6">
            <h3 className="mb-4 font-semibold">Performance Characteristics</h3>
            <div className="space-y-3">
              <PerformanceItem
                label="Idempotent Execution"
                value="Correlation ID based"
                description="Same workflow with same correlation ID produces identical results"
              />
              <PerformanceItem
                label="Checkpoint Frequency"
                value="Continuous"
                description="Intermediate states saved to disk for recovery"
              />
              <PerformanceItem
                label="Execution Contract"
                value="9-field schema"
                description="Deterministic input/output/state tracking"
              />
              <PerformanceItem
                label="Durability Level"
                value="fsync() guaranteed"
                description="All writes persisted to disk before acknowledgment"
              />
            </div>
          </div>

          <div className="rounded-lg border border-border bg-card p-6">
            <h3 className="mb-4 font-semibold">Resource Status</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Storage Validation</span>
                <span className={health.storage_valid ? "text-green-600" : "text-red-600"}>
                  {health.storage_valid ? "Valid" : "Invalid"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Request Handling</span>
                <span className={health.accepting_requests ? "text-green-600" : "text-red-600"}>
                  {health.accepting_requests ? "Accepting" : "Limited"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Overall Health</span>
                <span className={health.status === "healthy" ? "text-green-600" : "text-yellow-600"}>
                  {health.status === "healthy" ? "Healthy" : "Degraded"}
                </span>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function PerformanceItem({
  label,
  value,
  description,
}: {
  label: string;
  value: string;
  description: string;
}) {
  return (
    <div className="flex items-start justify-between border-t border-border pt-3 first:border-t-0 first:pt-0">
      <div>
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <span className="text-sm font-medium text-right ml-4">{value}</span>
    </div>
  );
}
