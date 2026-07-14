"use client";

import { useEffect, useState } from "react";
import { HealthResponse, runtimeApi } from "@/lib/api";
import { CheckCircle, AlertCircle, Zap, Database, Clock, Server } from "lucide-react";

export default function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadHealth = async () => {
      try {
        setLoading(true);
        const data = await runtimeApi.getHealth();
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
    <div className="space-y-8">
      <div>
        <h1 className="text-4xl font-bold text-white mb-2">
          DRT Runtime Dashboard
        </h1>
        <p className="text-drt-400">
          Production-Certified · Long-Term Support · v1.0.0-LTS
        </p>
      </div>

      {error && (
        <div className="bg-red-950 border border-red-700 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
          <div>
            <p className="font-semibold text-red-200">Connection Error</p>
            <p className="text-sm text-red-300">{error}</p>
            <p className="text-xs text-red-400 mt-2">
              Make sure the DRT Runtime is running at:{" "}
              <code className="bg-red-900 px-2 py-1 rounded">
                {process.env.NEXT_PUBLIC_RUNTIME_API || "http://localhost:5000"}
              </code>
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard
          label="Runtime Status"
          value={health?.status || "—"}
          icon={
            health?.status === "healthy" ? (
              <CheckCircle className="w-5 h-5 text-green-500" />
            ) : (
              <AlertCircle className="w-5 h-5 text-red-500" />
            )
          }
          loading={loading}
        />
        <StatCard
          label="Version"
          value={health?.runtime_version || "—"}
          icon={<Server className="w-5 h-5 text-blue-500" />}
          loading={loading}
        />
        <StatCard
          label="Uptime"
          value={formatUptime(health?.uptime_seconds || 0)}
          icon={<Clock className="w-5 h-5 text-yellow-500" />}
          loading={loading}
        />
        <StatCard
          label="Active Executions"
          value={String(health?.active_executions || 0)}
          icon={<Zap className="w-5 h-5 text-purple-500" />}
          loading={loading}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-drt-900 border border-drt-800 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Database className="w-5 h-5 text-blue-500" />
            Storage Status
          </h2>
          <div className="space-y-3">
            <HealthIndicator
              label="Storage Valid"
              status={health?.storage_valid || false}
            />
            <HealthIndicator
              label="Accepting Requests"
              status={health?.accepting_requests || false}
            />
            <p className="text-sm text-drt-400 mt-4">
              File-based persistence with WAL and fsync durability.
            </p>
          </div>
        </div>

        <div className="bg-drt-900 border border-drt-800 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Information</h2>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-drt-400">Runtime Version:</span>
              <span className="text-white font-mono">
                {health?.runtime_version || "—"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-drt-400">LTS Period:</span>
              <span className="text-white">2026-07-14 to 2028-01-14</span>
            </div>
            <div className="flex justify-between">
              <span className="text-drt-400">Storage Mode:</span>
              <span className="text-white">File-based + WAL</span>
            </div>
            <div className="flex justify-between">
              <span className="text-drt-400">Durability:</span>
              <span className="text-green-400">Guaranteed (fsync)</span>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-drt-900 border border-drt-800 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Getting Started</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <QuickLink
            title="Execute Workflow"
            description="Upload and execute a workflow"
            href="/workflows"
          />
          <QuickLink
            title="View Executions"
            description="Monitor running and completed workflows"
            href="/executions"
          />
          <QuickLink
            title="Check System Health"
            description="Inspect storage, persistence, and recovery status"
            href="/system"
          />
        </div>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon,
  loading,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  loading: boolean;
}) {
  return (
    <div className="bg-drt-900 border border-drt-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-drt-400 uppercase tracking-wider">
          {label}
        </span>
        {icon}
      </div>
      <div className="text-2xl font-bold text-white">
        {loading ? <span className="text-drt-500">•••</span> : value}
      </div>
    </div>
  );
}

function HealthIndicator({
  label,
  status,
}: {
  label: string;
  status: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-drt-300">{label}</span>
      <div className="flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full ${
            status ? "bg-green-500" : "bg-red-500"
          }`}
        ></div>
        <span className={status ? "text-green-400" : "text-red-400"}>
          {status ? "OK" : "Error"}
        </span>
      </div>
    </div>
  );
}

function QuickLink({
  title,
  description,
  href,
}: {
  title: string;
  description: string;
  href: string;
}) {
  return (
    <a
      href={href}
      className="bg-drt-800 hover:bg-drt-700 border border-drt-700 rounded-lg p-4 transition-colors group"
    >
      <h3 className="font-semibold text-white mb-1 group-hover:text-blue-400">
        {title}
      </h3>
      <p className="text-sm text-drt-400">{description}</p>
    </a>
  );
}

function formatUptime(seconds: number): string {
  if (!seconds) return "0s";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}
