"use client";

import { useState } from "react";
import { AdminPageHeader } from "@/components/admin/PageHeader";
import { AlertCircle, CheckCircle, Copy } from "lucide-react";

const API_ENDPOINTS = [
  {
    method: "GET",
    path: "/health",
    description: "Get runtime health status and system metrics",
    example: "http://localhost:5000/health",
    response: {
      status: "healthy | degraded",
      storage_valid: true,
      accepting_requests: true,
      version: "1.0.0",
      uptime_seconds: 3600,
    },
  },
  {
    method: "GET",
    path: "/execution/:id",
    description: "Get execution details by ID with full state and history",
    example: "http://localhost:5000/execution/exec-abc123",
    response: {
      id: "exec-abc123",
      status: "completed | running | failed | recovered",
      workflow_name: "example-workflow",
      correlation_id: "corr-xyz789",
      started_at: "2026-07-14T10:00:00Z",
      completed_at: "2026-07-14T10:05:00Z",
    },
  },
  {
    method: "POST",
    path: "/workflows",
    description: "Execute or dry-run a workflow from YAML definition",
    example: "http://localhost:5000/workflows",
    params: {
      workflow: "YAML workflow definition",
      correlation_id: "optional-correlation-id",
      dry_run: "true | false",
    },
    response: {
      execution_id: "exec-abc123",
      status: "queued",
      created_at: "2026-07-14T10:00:00Z",
    },
  },
  {
    method: "DELETE",
    path: "/graceful-shutdown",
    description: "Initiate graceful shutdown with WAL flush and cleanup",
    example: "http://localhost:5000/graceful-shutdown",
    response: {
      status: "shutting_down",
      message: "Graceful shutdown initiated",
    },
  },
];

export default function RuntimeApiPage() {
  const [expanded, setExpanded] = useState<number | null>(0);
  const [copied, setCopied] = useState<string | null>(null);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(text);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div>
      <AdminPageHeader
        title="API Reference"
        subtitle="DRT Runtime API endpoints and request/response documentation"
      />

      <div className="mb-6 rounded-lg border border-border bg-card p-4">
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-blue-500 mt-0.5 flex-shrink-0" />
          <div className="text-sm">
            <p className="font-medium text-foreground">API Base URL</p>
            <p className="text-muted-foreground mt-1">
              The DRT Runtime API is available at{" "}
              <code className="rounded-md bg-background px-2 py-1 font-mono">
                http://localhost:5000
              </code>
            </p>
            <p className="text-muted-foreground mt-2">
              No authentication required. All requests accept JSON. All responses return JSON with appropriate HTTP status codes.
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {API_ENDPOINTS.map((endpoint, index) => (
          <div
            key={index}
            className="rounded-lg border border-border bg-card overflow-hidden"
          >
            <button
              onClick={() => setExpanded(expanded === index ? null : index)}
              className="w-full px-6 py-4 flex items-center justify-between hover:bg-accent transition-colors"
            >
              <div className="flex items-center gap-4 flex-1 text-left">
                <span
                  className={`px-2 py-1 rounded-md text-xs font-semibold ${
                    endpoint.method === "GET"
                      ? "bg-blue-100 text-blue-900 dark:bg-blue-900 dark:text-blue-100"
                      : endpoint.method === "POST"
                      ? "bg-green-100 text-green-900 dark:bg-green-900 dark:text-green-100"
                      : "bg-red-100 text-red-900 dark:bg-red-900 dark:text-red-100"
                  }`}
                >
                  {endpoint.method}
                </span>
                <div className="flex-1">
                  <p className="font-mono text-sm font-medium">{endpoint.path}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {endpoint.description}
                  </p>
                </div>
              </div>
              <div className="text-muted-foreground">
                {expanded === index ? "−" : "+"}
              </div>
            </button>

            {expanded === index && (
              <div className="border-t border-border px-6 py-4 bg-background space-y-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                    Example Request
                  </p>
                  <div className="relative">
                    <code className="block font-mono text-xs bg-card border border-border rounded-md p-3 overflow-auto">
                      {endpoint.example}
                    </code>
                    <button
                      onClick={() => copyToClipboard(endpoint.example)}
                      className="absolute top-2 right-2 p-1.5 rounded-md bg-border hover:bg-border/80 transition-colors"
                      title="Copy to clipboard"
                    >
                      {copied === endpoint.example ? (
                        <CheckCircle className="h-4 w-4 text-green-600" />
                      ) : (
                        <Copy className="h-4 w-4 text-muted-foreground" />
                      )}
                    </button>
                  </div>
                </div>

                {endpoint.params && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                      Request Body Parameters
                    </p>
                    <div className="bg-card border border-border rounded-md p-3 space-y-2">
                      {Object.entries(endpoint.params).map(([key, value]) => (
                        <div key={key} className="text-xs">
                          <span className="font-mono font-medium">{key}</span>
                          <span className="text-muted-foreground ml-2">
                            {typeof value === "string" ? value : JSON.stringify(value)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                    Response Example
                  </p>
                  <pre className="font-mono text-xs bg-card border border-border rounded-md p-3 overflow-auto">
                    {JSON.stringify(endpoint.response, null, 2)}
                  </pre>
                </div>

                <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-md p-3">
                  <p className="text-xs text-blue-900 dark:text-blue-100">
                    <span className="font-semibold">Tip:</span> Use curl, fetch, or any HTTP client to test these endpoints. Include <code className="font-mono bg-blue-100 dark:bg-blue-900 px-1 rounded">Content-Type: application/json</code> for POST requests.
                  </p>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="mt-8 rounded-lg border border-border bg-card p-6">
        <h3 className="text-lg font-semibold mb-4">Integration Guide</h3>
        <div className="space-y-4 text-sm text-muted-foreground">
          <div>
            <p className="font-medium text-foreground mb-1">1. Health Checks</p>
            <p>
              Poll the <code className="font-mono bg-background px-1.5 py-0.5 rounded">/health</code> endpoint every 5-10 seconds to monitor runtime status and ensure continuous operation.
            </p>
          </div>
          <div>
            <p className="font-medium text-foreground mb-1">2. Workflow Execution</p>
            <p>
              Submit workflows to <code className="font-mono bg-background px-1.5 py-0.5 rounded">/workflows</code> with a correlation ID to ensure idempotent execution. Include the same correlation ID in retries.
            </p>
          </div>
          <div>
            <p className="font-medium text-foreground mb-1">3. Execution Tracking</p>
            <p>
              Query <code className="font-mono bg-background px-1.5 py-0.5 rounded">/execution/:id</code> to monitor execution progress, retrieve final state, and inspect failure details.
            </p>
          </div>
          <div>
            <p className="font-medium text-foreground mb-1">4. Graceful Shutdown</p>
            <p>
              Call <code className="font-mono bg-background px-1.5 py-0.5 rounded">/graceful-shutdown</code> to initiate controlled shutdown with WAL flush and resource cleanup.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
