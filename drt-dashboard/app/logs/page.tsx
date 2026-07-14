"use client";

import { useState } from "react";
import { FileText, Download } from "lucide-react";

export default function LogsPage() {
  const [level, setLevel] = useState("all");
  const [search, setSearch] = useState("");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white mb-2">Logs</h1>
        <p className="text-drt-400">
          Structured logs including execution logs, recovery logs, and errors.
        </p>
      </div>

      <div className="bg-drt-900 border border-drt-800 rounded-lg p-4 space-y-3">
        <div className="flex flex-col md:flex-row gap-3">
          <input
            type="text"
            placeholder="Search logs..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 bg-drt-800 border border-drt-700 rounded px-4 py-2 text-white placeholder-drt-500 focus:outline-none focus:border-blue-500"
          />
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="bg-drt-800 border border-drt-700 rounded px-4 py-2 text-white focus:outline-none focus:border-blue-500"
          >
            <option value="all">All Levels</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="error">Error</option>
            <option value="debug">Debug</option>
          </select>
          <button className="inline-flex items-center gap-2 bg-drt-800 hover:bg-drt-700 border border-drt-700 text-white px-4 py-2 rounded-lg transition-colors">
            <Download className="w-4 h-4" />
            Export
          </button>
        </div>
      </div>

      <div className="bg-drt-900 border border-drt-800 rounded-lg p-8 text-center">
        <FileText className="w-12 h-12 text-drt-600 mx-auto mb-4" />
        <p className="text-drt-400">No logs available</p>
        <p className="text-sm text-drt-500">
          Execute workflows to generate logs.
        </p>
      </div>
    </div>
  );
}
