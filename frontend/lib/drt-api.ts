const DRT_API_URL = process.env.NEXT_PUBLIC_DRT_RUNTIME_API || "http://localhost:5000";

export interface DRTHealth {
  status: string;
  version?: string;
  uptime_seconds?: number;
  storage_valid: boolean;
  accepting_requests: boolean;
  active_executions?: number;
}

export interface DRTExecution {
  execution_id: string;
  correlation_id?: string;
  workflow_version?: string;
  runtime_version?: string;
  started_at: string;
  finished_at?: string;
  duration_ms?: number;
  status: string;
  checksum?: string;
  workflow_id?: string;
  workflow_name?: string;
  current_step?: string;
  step_history?: Array<{
    name: string;
    started_at: string;
    finished_at?: string;
    duration_ms: number;
    status: string;
    result?: any;
    error?: string;
  }>;
  recovery_count?: number;
  retry_count?: number;
  audit_trail?: Array<{
    timestamp: string;
    event: string;
    details?: any;
  }>;
  error?: string;
}

async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = 5000
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail ?? `Request failed: ${response.status}`);
    }

    return response;
  } finally {
    clearTimeout(timeoutId);
  }
}

export const drtApi = {
  async getHealth(): Promise<DRTHealth> {
    const response = await fetchWithTimeout(`${DRT_API_URL}/health`, {}, 5000);
    return response.json();
  },

  async getExecution(executionId: string): Promise<DRTExecution> {
    const response = await fetchWithTimeout(
      `${DRT_API_URL}/workflow/${executionId}`,
      {},
      5000
    );
    return response.json();
  },

  async dryRunWorkflow(workflow: any): Promise<any> {
    const response = await fetchWithTimeout(
      `${DRT_API_URL}/workflow?dry_run=true`,
      {
        method: "POST",
        body: JSON.stringify({ workflow }),
      },
      10000
    );
    return response.json();
  },

  async executeWorkflow(workflow: any, correlationId?: string): Promise<DRTExecution> {
    const response = await fetchWithTimeout(
      `${DRT_API_URL}/workflow`,
      {
        method: "POST",
        body: JSON.stringify({
          workflow,
          ...(correlationId && { correlation_id: correlationId }),
        }),
      },
      30000
    );
    return response.json();
  },

  async gracefulShutdown(): Promise<void> {
    const response = await fetchWithTimeout(
      `${DRT_API_URL}/health`,
      { method: "GET" },
      5000
    );
    if (response.status === 200) {
      console.log("Runtime health check passed - graceful shutdown not required in development");
    }
  },
};
