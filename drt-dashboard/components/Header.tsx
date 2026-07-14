"use client";

import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle, Clock } from "lucide-react";

export function Header() {
  const [health, setHealth] = useState<{
    status: string;
    uptime: number;
  } | null>(null);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_RUNTIME_API}/health`
        );
        const data = await response.json();
        setHealth(data);
      } catch (error) {
        console.error("Failed to fetch health:", error);
      }
    };

    fetchHealth();
    const interval = setInterval(fetchHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  const isHealthy = health?.status === "healthy";

  return (
    <header className="h-16 bg-drt-900 border-b border-drt-800 flex items-center justify-between px-6">
      <div className="flex items-center gap-3">
        {isHealthy ? (
          <CheckCircle className="w-5 h-5 text-green-500" />
        ) : (
          <AlertCircle className="w-5 h-5 text-red-500" />
        )}
        <span className="text-sm font-medium text-drt-300">
          Runtime Status: <span className="text-white font-semibold">{health?.status || "loading"}</span>
        </span>
      </div>

      {health && (
        <div className="flex items-center gap-4 text-sm text-drt-400">
          <div className="flex items-center gap-1">
            <Clock className="w-4 h-4" />
            <span>Uptime: {formatUptime(health.uptime)}</span>
          </div>
        </div>
      )}
    </header>
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
