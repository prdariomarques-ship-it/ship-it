"use client";

import { useEffect, useState } from "react";
import { drtApi, type DRTHealth } from "@/lib/drt-api";
import { AdminPageHeader } from "@/components/admin/PageHeader";
import { ErrorState } from "@/components/admin/ErrorState";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { MetricCard } from "@/components/admin/MetricCard";
import { Database, HardDrive, CheckCircle, AlertCircle } from "lucide-react";

export default function RuntimePersistencePage() {
  const [health, setHealth] = useState<DRTHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadHealth = async () => {
      try {
        const data = await drtApi.getHealth();
        setHealth(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load persistence data");
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
        title="Persistence"
        subtitle="Storage validation, checkpoints, WAL, and durability status"
      />

      {error && (
        <ErrorState message={error} onRetry={() => setLoading(true)} />
      )}

      {loading ? (
        <LoadingGrid count={4} />
      ) : health ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <MetricCard
              label="Storage Valid"
              value={health.storage_valid ? "Valid" : "Invalid"}
              icon={Database}
              tone={health.storage_valid ? "success" : "destructive"}
            />
            <MetricCard
              label="Accepting Requests"
              value={health.accepting_requests ? "Yes" : "No"}
              icon={HardDrive}
              tone={health.accepting_requests ? "success" : "destructive"}
            />
          </div>

          <div className="rounded-lg border border-border bg-card p-6">
            <h3 className="mb-4 font-semibold">Durability Guarantees</h3>
            <div className="space-y-3">
              <PersistenceItem
                label="fsync() Guaranteed"
                status={true}
                description="All writes are synchronized to disk"
              />
              <PersistenceItem
                label="Atomic Writes"
                status={true}
                description="All-or-nothing semantics for execution contracts"
              />
              <PersistenceItem
                label="Write-Ahead Log (WAL)"
                status={true}
                description="Transactions logged before execution"
              />
              <PersistenceItem
                label="Crash Safe"
                status={true}
                description="Recovery from system failures guaranteed"
              />
            </div>
          </div>

          <div className="rounded-lg border border-border bg-card p-6">
            <h3 className="mb-4 font-semibold">Storage Configuration</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Storage Backend</span>
                <span className="font-medium">File-based Persistence</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Checkpoint Strategy</span>
                <span className="font-medium">Continuous Checkpointing</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Recovery Mode</span>
                <span className="font-medium">Automatic WAL Replay</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Validation</span>
                <span className="font-medium">SHA256 Checksum</span>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function PersistenceItem({
  label,
  status,
  description,
}: {
  label: string;
  status: boolean;
  description: string;
}) {
  return (
    <div className="flex items-start justify-between">
      <div>
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <div className="flex items-center gap-1">
        {status ? (
          <CheckCircle className="h-4 w-4 text-green-600" />
        ) : (
          <AlertCircle className="h-4 w-4 text-red-600" />
        )}
      </div>
    </div>
  );
}
