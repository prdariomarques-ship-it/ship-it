"use client";

import { useState } from "react";
import { Play, AlertCircle } from "lucide-react";

export default function WorkflowsPage() {
  const [yaml, setYaml] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  const handleDryRun = async () => {
    if (!yaml.trim()) {
      setError("Please enter a workflow YAML");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_RUNTIME_API}/workflows`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(YAML.parse(yaml)),
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to validate");
    } finally {
      setLoading(false);
    }
  };

  const handleExecute = async () => {
    if (!yaml.trim()) {
      setError("Please enter a workflow YAML");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_RUNTIME_API}/workflows`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(YAML.parse(yaml)),
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Execution failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white mb-2">Workflow Management</h1>
        <p className="text-drt-400">
          Upload YAML workflows, perform dry runs, and execute them.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <label className="block text-sm font-semibold text-white mb-2">
            Workflow YAML
          </label>
          <textarea
            value={yaml}
            onChange={(e) => setYaml(e.target.value)}
            placeholder={`name: example-workflow
workflow_version: "1.0"
runtime_version: "1.0"
owner: operator
timeout: 300
steps:
  - name: step-1
    type: system`}
            className="w-full h-64 bg-drt-800 border border-drt-700 rounded-lg p-4 text-white font-mono text-sm placeholder-drt-500 focus:outline-none focus:border-blue-500"
          />
          {error && (
            <div className="mt-2 bg-red-950 border border-red-700 rounded p-3 flex gap-2">
              <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-red-200">Error</p>
                <p className="text-xs text-red-300">{error}</p>
              </div>
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-semibold text-white mb-2">
            Result
          </label>
          <pre className="w-full h-64 bg-drt-800 border border-drt-700 rounded-lg p-4 text-drt-300 font-mono text-xs overflow-auto">
            {result ? JSON.stringify(result, null, 2) : "Result will appear here..."}
          </pre>
        </div>
      </div>

      <div className="flex gap-2">
        <button
          onClick={handleDryRun}
          disabled={loading}
          className="inline-flex items-center gap-2 bg-yellow-600 hover:bg-yellow-700 disabled:bg-drt-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
        >
          <Play className="w-4 h-4" />
          {loading ? "Processing..." : "Dry Run"}
        </button>
        <button
          onClick={handleExecute}
          disabled={loading}
          className="inline-flex items-center gap-2 bg-green-600 hover:bg-green-700 disabled:bg-drt-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
        >
          <Play className="w-4 h-4" />
          {loading ? "Processing..." : "Execute"}
        </button>
      </div>
    </div>
  );
}

// Simple YAML parser for demonstration
const YAML = {
  parse: (yaml: string) => {
    const obj: any = {};
    yaml.split("\n").forEach((line) => {
      const match = line.match(/^(\w+):\s*(.+)$/);
      if (match) {
        const [, key, value] = match;
        obj[key] = value.replace(/^["']|["']$/g, "");
      }
    });
    return obj;
  },
};
