"use client";

import { useState } from "react";
import { Activity, Search } from "lucide-react";

export default function ExecutionsPage() {
  const [searchId, setSearchId] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white mb-2">Executions</h1>
        <p className="text-drt-400">
          Monitor all workflow executions, including running, completed, recovered, and failed.
        </p>
      </div>

      <div className="bg-drt-900 border border-drt-800 rounded-lg p-4">
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-3 w-4 h-4 text-drt-400" />
            <input
              type="text"
              placeholder="Search execution ID or correlation ID..."
              value={searchId}
              onChange={(e) => setSearchId(e.target.value)}
              className="w-full bg-drt-800 border border-drt-700 rounded px-4 py-2 pl-10 text-white placeholder-drt-500 focus:outline-none focus:border-blue-500"
            />
          </div>
          <div className="flex gap-2">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-drt-800 border border-drt-700 rounded px-4 py-2 text-white focus:outline-none focus:border-blue-500"
            >
              <option value="all">All Status</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="recovered">Recovered</option>
              <option value="failed">Failed</option>
            </select>
          </div>
        </div>
      </div>

      <div className="bg-drt-900 border border-drt-800 rounded-lg p-8 text-center">
        <Activity className="w-12 h-12 text-drt-600 mx-auto mb-4" />
        <p className="text-drt-400 mb-2">No executions yet</p>
        <p className="text-sm text-drt-500">
          Execute a workflow to start tracking executions here.
        </p>
        <a
          href="/workflows"
          className="inline-block mt-4 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          Execute Workflow
        </a>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <MetricBox label="Total Executions" value="0" />
        <MetricBox label="Running" value="0" />
        <MetricBox label="Completed" value="0" />
      </div>
    </div>
  );
}

function MetricBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-drt-900 border border-drt-800 rounded-lg p-4">
      <p className="text-xs text-drt-400 uppercase mb-1">{label}</p>
      <p className="text-2xl font-bold text-white">{value}</p>
    </div>
  );
}
