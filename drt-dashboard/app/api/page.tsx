"use client";

export default function ApiPage() {
  const endpoints = [
    {
      method: "GET",
      path: "/health",
      description: "Runtime health status and metrics",
    },
    {
      method: "POST",
      path: "/workflows",
      description: "Execute or dry-run a workflow",
    },
    {
      method: "GET",
      path: "/execution/{execution_id}",
      description: "Get execution details and state",
    },
    {
      method: "DELETE",
      path: "/graceful-shutdown",
      description: "Graceful shutdown with 30s timeout",
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white mb-2">API Reference</h1>
        <p className="text-drt-400">
          Endpoint browser and live testing for the DRT Runtime HTTP API.
        </p>
      </div>

      <div className="bg-blue-950 border border-blue-700 rounded-lg p-4">
        <p className="text-sm text-blue-200">
          <strong>Base URL:</strong>{" "}
          <code className="bg-blue-900 px-2 py-1 rounded">
            {process.env.NEXT_PUBLIC_RUNTIME_API || "http://localhost:5000"}
          </code>
        </p>
      </div>

      <div className="space-y-3">
        {endpoints.map((endpoint, idx) => (
          <div
            key={idx}
            className="bg-drt-900 border border-drt-800 rounded-lg p-4 hover:border-drt-700 transition-colors"
          >
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0">
                <span
                  className={`inline-block px-3 py-1 rounded text-xs font-semibold ${
                    endpoint.method === "GET"
                      ? "bg-blue-900 text-blue-200"
                      : endpoint.method === "POST"
                      ? "bg-green-900 text-green-200"
                      : "bg-red-900 text-red-200"
                  }`}
                >
                  {endpoint.method}
                </span>
              </div>
              <div className="flex-1">
                <code className="text-white font-mono text-sm">{endpoint.path}</code>
                <p className="text-drt-400 text-sm mt-1">{endpoint.description}</p>
              </div>
              <button className="bg-drt-800 hover:bg-drt-700 text-white px-3 py-2 rounded text-sm transition-colors">
                Test
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="bg-drt-900 border border-drt-800 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Authentication</h2>
        <p className="text-drt-300 text-sm mb-3">
          The DRT Runtime API requires no authentication. All endpoints are directly accessible.
        </p>
        <div className="bg-drt-800 border border-drt-700 rounded p-3">
          <code className="text-drt-100 text-xs">
            curl {process.env.NEXT_PUBLIC_RUNTIME_API || "http://localhost:5000"}/health
          </code>
        </div>
      </div>
    </div>
  );
}
