import { vi } from "vitest";

import { apiFetch } from "@/hooks/useApi";

type Handler = unknown | ((path: string, options?: RequestInit) => unknown);

/** Error shaped like hooks/useApi.ts's ApiError, without importing the (mocked) module. */
export function apiError(message: string, status: number, detail?: unknown): Error {
  return Object.assign(new Error(message), { name: "ApiError", status, detail: detail ?? message });
}

/**
 * Routes the mocked `apiFetch` by path prefix (longest prefix wins). A handler may be a value, a function, or an
 * Error to reject with. An unrouted path rejects loudly so a test never silently depends on a missing endpoint.
 */
export function serve(routes: Record<string, Handler>) {
  const calls: Array<{ path: string; options?: RequestInit }> = [];
  const keys = Object.keys(routes).sort((a, b) => b.length - a.length);
  vi.mocked(apiFetch).mockImplementation((async (path: string, options?: RequestInit) => {
    calls.push({ path, options });
    const key = keys.find((candidate) => path.startsWith(candidate));
    if (key === undefined) throw new Error(`unrouted request in test: ${path}`);
    const handler = routes[key];
    const value = typeof handler === "function" ? (handler as (p: string, o?: RequestInit) => unknown)(path, options) : handler;
    if (value instanceof Error) throw value;
    return value;
  }) as unknown as typeof apiFetch);
  return {
    calls,
    paths: () => calls.map((call) => call.path),
    posts: () => calls.filter((call) => call.options?.method === "POST" || call.options?.method === "PUT"),
  };
}

export const TASK = {
  id: "11111111-aaaa-bbbb-cccc-000000000001",
  objective: "Enviar contrato revisado ao cliente",
  status: "PAUSED",
  agentId: "agent-1",
  createdAt: "2026-10-19T10:00:00.000Z",
  updatedAt: "2026-10-19T10:00:05.000Z",
};

export const DARIUS_OK = {
  configured: true,
  reachable: true,
  circuit: "closed",
  latency_ms: 12.5,
  base_url: "http://127.0.0.1:3000",
  service_credential_configured: true,
  operator_credential_configured: true,
  checked_at: "2026-10-19T12:00:00.000Z",
  error: null,
};

export const ROUTING = {
  enabled: true,
  darius_configured: true,
  reply_timeout_seconds: 900,
  global_suspended: false,
  global_suspension_reason: null,
  instances: [
    { instance: "store", routed_to_darius: true, suspended: false, suspension_reason: null },
    { instance: "personal", routed_to_darius: false, suspended: true, suspension_reason: "manutenção do número" },
  ],
  unknown_routed_instances: [],
};

export const LINKS = {
  items: [
    {
      id: 2,
      instance: "store",
      status: "failed",
      darius_task_id: "t-2",
      darius_status: "FAILED",
      message_id: 11,
      contact_id: 5,
      attempts: 3,
      last_error: "Exceeded maximum iterations",
      reply_chars: null,
      history: [],
      created_at: "2026-10-19T11:00:00.000Z",
      finished_at: "2026-10-19T11:01:00.000Z",
    },
    {
      id: 1,
      instance: "store",
      status: "reply_queued",
      darius_task_id: "t-1",
      darius_status: "COMPLETED",
      message_id: 10,
      contact_id: 5,
      attempts: 1,
      last_error: null,
      reply_chars: 42,
      history: [],
      created_at: "2026-10-19T10:00:00.000Z",
      finished_at: "2026-10-19T10:00:30.000Z",
    },
  ],
  counts: { failed: 1, reply_queued: 1, expired: 2 },
  next_offset: null,
};

export const SUSPENSION = {
  global_suspended: false,
  global_forced_by_environment: false,
  suspended_instances: ["personal"],
  configured_instances: ["store", "personal"],
  details: [{ scope: "instance:personal", reason: "manutenção do número", actor_id: 1, since: "2026-10-19T09:00:00+00:00" }],
};
