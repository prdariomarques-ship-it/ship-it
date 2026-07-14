"use client";

import { useState } from "react";
import { AdminPageHeader } from "@/components/admin/PageHeader";
import { ErrorState } from "@/components/admin/ErrorState";
import { drtApi } from "@/lib/drt-api";
import { Loader2 } from "lucide-react";

export default function RuntimeWorkflowsPage() {
  const [yaml, setYaml] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"dry-run" | "execute" | null>(null);

  async function handleDryRun() {
    if (!yaml.trim()) {
      setError("Please enter a YAML workflow definition");
      return;
    }

    setLoading(true);
    setError(null);
    setMode("dry-run");
    setResult(null);

    try {
      const workflow = parseYaml(yaml);
      const dryRunResult = await drtApi.dryRunWorkflow(workflow);
      setResult(dryRunResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dry run failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleExecute() {
    if (!yaml.trim()) {
      setError("Please enter a YAML workflow definition");
      return;
    }

    setLoading(true);
    setError(null);
    setMode("execute");
    setResult(null);

    try {
      const workflow = parseYaml(yaml);
      const correlationId = `exec-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      const execution = await drtApi.executeWorkflow(workflow, correlationId);
      setResult(execution);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workflow execution failed");
    } finally {
      setLoading(false);
    }
  }

  function parseYaml(yamlStr: string): any {
    try {
      const lines = yamlStr.split("\n").filter((line) => line.trim());
      const obj: any = {};
      for (const line of lines) {
        const [key, value] = line.split(":").map((s) => s.trim());
        if (key && value) obj[key] = value.replace(/^["']|["']$/g, "");
      }
      return obj;
    } catch {
      throw new Error("Invalid YAML format");
    }
  }

  return (
    <div>
      <AdminPageHeader
        title="Workflow Management"
        subtitle="Upload YAML workflows, perform dry runs, and execute them"
      />

      {error && <ErrorState message={error} onRetry={() => setError(null)} />}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div>
          <label className="mb-2 block text-sm font-medium" htmlFor="yaml-input">
            Workflow YAML
          </label>
          <textarea
            id="yaml-input"
            value={yaml}
            onChange={(e) => setYaml(e.target.value)}
            disabled={loading}
            placeholder={`name: example
workflow_version: "1.0"
owner: operator
timeout: 300
steps:
  - name: step-1
    type: system`}
            className="h-64 w-full rounded-md border border-input bg-background p-3 font-mono text-sm disabled:opacity-50"
          />
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium" htmlFor="result-output">
            Result
          </label>
          <pre
            id="result-output"
            className="h-64 w-full rounded-md border border-input bg-background p-3 font-mono text-xs overflow-auto"
          >
            {loading ? (
              <span className="text-muted-foreground">
                {mode === "dry-run" ? "Running dry run..." : "Executing workflow..."}
              </span>
            ) : result ? (
              JSON.stringify(result, null, 2)
            ) : (
              <span className="text-muted-foreground">Result will appear here...</span>
            )}
          </pre>
        </div>
      </div>

      <div className="mt-6 flex gap-2">
        <button
          onClick={handleDryRun}
          disabled={loading}
          className="flex items-center gap-2 rounded-md bg-yellow-600 hover:bg-yellow-700 disabled:opacity-50 text-white px-4 py-2 text-sm font-medium transition-colors"
        >
          {loading && mode === "dry-run" && <Loader2 className="h-4 w-4 animate-spin" />}
          Dry Run
        </button>
        <button
          onClick={handleExecute}
          disabled={loading}
          className="flex items-center gap-2 rounded-md bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white px-4 py-2 text-sm font-medium transition-colors"
        >
          {loading && mode === "execute" && <Loader2 className="h-4 w-4 animate-spin" />}
          Execute
        </button>
      </div>
    </div>
  );
}
