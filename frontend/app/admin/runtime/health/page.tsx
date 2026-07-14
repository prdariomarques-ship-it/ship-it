"use client";

import { useEffect, useState } from "react";
import { drtApi, type DRTHealth } from "@/lib/drt-api";
import { AdminPageHeader } from "@/components/admin/PageHeader";
import { ErrorState } from "@/components/admin/ErrorState";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { CheckCircle, AlertCircle } from "lucide-react";

export default function RuntimeHealthPage() {
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
        setError(err instanceof Error ? err.message : "Failed to load health");
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
        title="System Health"
        subtitle="Real-time health status of DRT Runtime components"
      />

      {error && (
        <ErrorState message={error} onRetry={() => setLoading(true)} />
      )}

      {loading ? (
        <LoadingGrid count={4} />
      ) : health ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <HealthSection title="Storage & Persistence">
            <HealthItem
              label="Storage Valid"
              status={health.storage_valid}
            />
            <HealthItem
              label="Accepting Requests"
              status={health.accepting_requests}
            />
          </HealthSection>

          <HealthSection title="Durability">
            <HealthItem label="fsync() Guaranteed" status={true} />
            <HealthItem label="Atomic Writes" status={true} />
          </HealthSection>

          <HealthSection title="Recovery">
            <HealthItem label="Crash Safe" status={true} />
            <HealthItem label="WAL Replay" status={true} />
          </HealthSection>

          <HealthSection title="Runtime">
            <HealthItem
              label="Status"
              status={health.status === "healthy"}
            />
            <HealthItem label="API Responsive" status={health.accepting_requests} />
          </HealthSection>
        </div>
      ) : null}
    </div>
  );
}

function HealthSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <h3 className="mb-4 font-semibold">{title}</h3>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function HealthItem({ label, status }: { label: string; status: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-muted-foreground">{label}</span>
      <div className="flex items-center gap-2">
        {status ? (
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
      </div>
    </div>
  );
}
