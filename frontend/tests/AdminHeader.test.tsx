import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useApi", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/hooks/useApi";
import { AdminHeader } from "@/components/admin/AdminHeader";
import { renderWithQueryClient } from "./test-utils";

const mockedApiFetch = vi.mocked(apiFetch);

describe("AdminHeader", () => {
  it("shows the logged-in user's email and a 'verificando' state before status loads", () => {
    mockedApiFetch.mockReturnValue(new Promise(() => {})); // never resolves
    renderWithQueryClient(<AdminHeader userEmail="admin@dario.os" />);
    expect(screen.getByText("admin@dario.os")).toBeInTheDocument();
    expect(screen.getByText("verificando…")).toBeInTheDocument();
  });

  it("shows 'todos os sistemas operacionais' when every component is online", async () => {
    mockedApiFetch.mockResolvedValue([
      { name: "backend", online: true, detail: "", latency_ms: 0, last_heartbeat: new Date().toISOString() },
      { name: "database", online: true, detail: "ok", latency_ms: 1, last_heartbeat: new Date().toISOString() },
    ]);
    renderWithQueryClient(<AdminHeader userEmail="admin@dario.os" />);
    await waitFor(() => expect(screen.getByText("todos os sistemas operacionais")).toBeInTheDocument());
  });

  it("shows 'atenção necessária' when any component is offline", async () => {
    mockedApiFetch.mockResolvedValue([
      { name: "backend", online: true, detail: "", latency_ms: 0, last_heartbeat: new Date().toISOString() },
      { name: "qdrant", online: false, detail: "down", latency_ms: null, last_heartbeat: new Date().toISOString() },
    ]);
    renderWithQueryClient(<AdminHeader userEmail="admin@dario.os" />);
    await waitFor(() => expect(screen.getByText("atenção necessária")).toBeInTheDocument());
  });
});
