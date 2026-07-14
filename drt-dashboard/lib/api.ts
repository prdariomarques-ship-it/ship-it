const API_BASE = process.env.NEXT_PUBLIC_RUNTIME_API || "http://localhost:5000";

export interface ExecutionResponse {
  execution_id: string;
  correlation_id?: string;
  workflow_version: string;
  runtime_version: string;
  started_at: string;
  finished_at?: string;
  duration_ms: number;
  status: string;
  checksum: string;
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
  recovery_count: number;
  retry_count: number;
  audit_trail?: Array<{
    timestamp: string;
    event: string;
    details?: any;
  }>;
  error?: string;
}

export interface HealthResponse {
  status: string;
  runtime_version: string;
  uptime_seconds: number;
  storage_valid: boolean;
  accepting_requests: boolean;
  active_executions: number;
}

export interface DryRunResponse {
  workflow: {
    name: string;
    workflow_version: string;
    runtime_version: string;
    owner: string;
    timeout: number;
    retry_policy: string;
    created_at: string;
    description: string;
    steps: Array<{
      name: string;
      type: string;
      config: any;
    }>;
  };
  step_sequence: string[];
  estimated_duration_ms: number;
  status: string;
}

export const runtimeApi = {
  async getHealth(): Promise<HealthResponse> {
    const response = await fetch(`${API_BASE}/health`);
    if (!response.ok) throw new Error("Failed to fetch health");
    return response.json();
  },

  async getExecution(executionId: string): Promise<ExecutionResponse> {
    const response = await fetch(`${API_BASE}/execution/${executionId}`);
    if (!response.ok) throw new Error("Failed to fetch execution");
    return response.json();
  },

  async listExecutions(): Promise<ExecutionResponse[]> {
    return []; // Would need a list endpoint in the Runtime
  },

  async dryRun(workflow: any): Promise<DryRunResponse> {
    const response = await fetch(`${API_BASE}/workflows`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...workflow, dry_run: true }),
    });
    if (!response.ok) throw new Error("Dry run failed");
    return response.json();
  },

  async executeWorkflow(
    workflow: any,
    correlationId?: string
  ): Promise<ExecutionResponse> {
    const response = await fetch(`${API_BASE}/workflows`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...workflow,
        correlation_id: correlationId,
      }),
    });
    if (!response.ok) throw new Error("Execution failed");
    return response.json();
  },

  async gracefulShutdown(): Promise<void> {
    const response = await fetch(`${API_BASE}/graceful-shutdown`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error("Shutdown failed");
  },
};
