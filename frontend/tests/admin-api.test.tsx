import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useApi", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/hooks/useApi";
import {
  useAdminAgents,
  useAdminExecutions,
  useAdminGoogle,
  useAdminIndex,
  useAdminLogs,
  useAdminMemory,
  useAdminMetrics,
  useAdminStatus,
  useAdminSystem,
  useAdminTools,
  useAdminUsers,
  useAdminWhatsApp,
} from "@/lib/admin-api";
import { createTestQueryClient } from "./test-utils";

const mockedApiFetch = vi.mocked(apiFetch);

function wrapper({ children }: { children: React.ReactNode }) {
  const client = createTestQueryClient();
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("lib/admin-api hooks", () => {
  it("useAdminStatus calls /admin/status", async () => {
    mockedApiFetch.mockResolvedValue([]);
    renderHook(() => useAdminStatus(), { wrapper });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledWith("/admin/status"));
  });

  it("useAdminUsers calls /admin/users", async () => {
    mockedApiFetch.mockResolvedValue([]);
    renderHook(() => useAdminUsers(), { wrapper });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledWith("/admin/users"));
  });

  it("useAdminLogs builds a query string only from the filters that are actually set", async () => {
    mockedApiFetch.mockResolvedValue([]);
    renderHook(() => useAdminLogs({ level: "error", search: "timeout" }), { wrapper });
    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/admin/logs?level=error&search=timeout&limit=100")
    );
  });

  it("useAdminLogs omits unset filters entirely rather than sending empty params", async () => {
    mockedApiFetch.mockResolvedValue([]);
    renderHook(() => useAdminLogs({}), { wrapper });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledWith("/admin/logs?limit=100"));
  });

  it("useAdminExecutions includes the agent filter only when provided", async () => {
    mockedApiFetch.mockResolvedValue([]);
    renderHook(() => useAdminExecutions({ period: "7d", agent: "personal" }), { wrapper });
    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/admin/executions?period=7d&agent=personal")
    );
  });

  it("useAdminExecutions without an agent filter omits it", async () => {
    mockedApiFetch.mockResolvedValue([]);
    renderHook(() => useAdminExecutions({ period: "today" }), { wrapper });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledWith("/admin/executions?period=today"));
  });

  it("useAdminIndex calls /admin", async () => {
    mockedApiFetch.mockResolvedValue({});
    renderHook(() => useAdminIndex(), { wrapper });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledWith("/admin"));
  });

  it("useAdminSystem calls /admin/system", async () => {
    mockedApiFetch.mockResolvedValue({});
    renderHook(() => useAdminSystem(), { wrapper });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledWith("/admin/system"));
  });

  it("useAdminAgents calls /admin/agents", async () => {
    mockedApiFetch.mockResolvedValue([]);
    renderHook(() => useAdminAgents(), { wrapper });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledWith("/admin/agents"));
  });

  it("useAdminTools calls /admin/tools", async () => {
    mockedApiFetch.mockResolvedValue([]);
    renderHook(() => useAdminTools(), { wrapper });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledWith("/admin/tools"));
  });

  it("useAdminGoogle calls /admin/google", async () => {
    mockedApiFetch.mockResolvedValue({});
    renderHook(() => useAdminGoogle(), { wrapper });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledWith("/admin/google"));
  });

  it("useAdminMemory calls /admin/memory", async () => {
    mockedApiFetch.mockResolvedValue({});
    renderHook(() => useAdminMemory(), { wrapper });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledWith("/admin/memory"));
  });

  it("useAdminMetrics calls /admin/metrics", async () => {
    mockedApiFetch.mockResolvedValue({ timestamp: "now", metrics: {} });
    renderHook(() => useAdminMetrics(), { wrapper });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledWith("/admin/metrics"));
  });

  it("useAdminWhatsApp calls /admin/whatsapp", async () => {
    mockedApiFetch.mockResolvedValue({});
    renderHook(() => useAdminWhatsApp(), { wrapper });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledWith("/admin/whatsapp"));
  });
});
