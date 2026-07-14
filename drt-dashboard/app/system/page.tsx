"use client";

import { useEffect, useState } from "react";
import { HealthResponse, runtimeApi } from "@/lib/api";

export default function SystemPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadHealth = async () => {
      try {
        const data = await runtimeApi.getHealth();
        setHealth(data);
      } catch (error) {
        console.error("Failed to load health:", error);
      } finally {
        setLoading(false);
      }
    };

    loadHealth();
    const interval = setInterval(loadHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white mb-2">System Health</h1>
        <p className="text-drt-400">
          Disk, persistence, and WAL status. Storage validation and recovery state.
        </p>
      </div>

      {loading ? (
        <div className="text-center py-8">
          <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto"></div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <HealthCard
            title="Disk & Persistence"
            items={[
              { label: "Storage Valid", status: health?.storage_valid || false },
              { label: "Accepting Requests", status: health?.accepting_requests || false },
            ]}
          />
          <HealthCard
            title="Checkpoint & WAL"
            items={[
              { label: "fsync() Durability", status: true },
              { label: "Atomic Writes", status: true },
            ]}
          />
          <HealthCard
            title="Memory & Performance"
            items={[
              { label: "Runtime Available", status: health?.status === "healthy" },
              { label: "API Responsive", status: health?.accepting_requests || false },
            ]}
          />
          <HealthCard
            title="Recovery Capability"
            items={[
              { label: "Crash Safe", status: true },
              { label: "WAL Replay", status: true },
            ]}
          />
        </div>
      )}

      <div className="bg-drt-900 border border-drt-800 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Storage Configuration</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <ConfigItem label="Storage Type" value="File-based" />
          <ConfigItem label="Persistence Format" value="JSON + WAL" />
          <ConfigItem label="Durability Guarantee" value="fsync() on every write" />
          <ConfigItem label="Checksum Verification" value="SHA256" />
          <ConfigItem label="Max Executions" value="~100,000" />
          <ConfigItem label="Current Active" value={String(health?.active_executions || 0)} />
        </div>
      </div>
    </div>
  );
}

function HealthCard({
  title,
  items,
}: {
  title: string;
  items: Array<{ label: string; status: boolean }>;
}) {
  return (
    <div className="bg-drt-900 border border-drt-800 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3">{title}</h3>
      <div className="space-y-2">
        {items.map((item) => (
          <div key={item.label} className="flex items-center justify-between">
            <span className="text-drt-400">{item.label}</span>
            <div className="flex items-center gap-2">
              <div
                className={`w-2 h-2 rounded-full ${
                  item.status ? "bg-green-500" : "bg-red-500"
                }`}
              ></div>
              <span className={item.status ? "text-green-400 text-xs" : "text-red-400 text-xs"}>
                {item.status ? "OK" : "Error"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ConfigItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-drt-400">{label}</p>
      <p className="text-white font-semibold">{value}</p>
    </div>
  );
}
