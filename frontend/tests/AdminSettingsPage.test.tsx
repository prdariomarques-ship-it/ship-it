import type { ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useApi", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/hooks/useApi";
import AdminSettingsPage from "@/app/admin/settings/page";
import { AdminToastProvider } from "@/hooks/use-toast";
import { createTestQueryClient } from "./test-utils";

const mockedApiFetch = vi.mocked(apiFetch);

function renderPage(ui: ReactNode) {
  const client = createTestQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <AdminToastProvider>{ui}</AdminToastProvider>
    </QueryClientProvider>
  );
}

const SYSTEM_INFO = {
  app_name: "Dario OS",
  version: "1.4.0",
  environment: "production",
  commit: "abc123",
  branch: "master",
  tag: null,
  uptime_seconds: 100,
  cpu_percent: null,
  memory_used_mb: null,
  memory_total_mb: null,
  memory_percent: null,
  disk_used_gb: null,
  disk_total_gb: null,
  disk_percent: null,
  db_pool_size: null,
  db_pool_checked_out: null,
  llm_provider: "openai",
  embedding_provider: "openai",
  whatsapp_provider: "openwa",
  mail_provider: "gmail",
  calendar_provider: "google",
  contacts_provider: "google",
  drive_provider: "google",
  auto_reply_enabled: true,
  jobs_enabled: true,
};

const BEHAVIOR_SETTINGS = [
  {
    key: "auto_reply_enabled",
    value: true,
    description: "Resposta automática do assistente a mensagens recebidas no WhatsApp.",
    category: "behavior",
    editable: true,
    updated_at: null,
    updated_by: null,
  },
  {
    key: "jobs_enabled",
    value: true,
    description: "Fila de jobs em segundo plano (worker).",
    category: "behavior",
    editable: false,
    updated_at: null,
    updated_by: null,
  },
  {
    key: "environment",
    value: "production",
    description: "Ambiente de execução do backend.",
    category: "behavior",
    editable: false,
    updated_at: null,
    updated_by: null,
  },
];

function mockFetchImplementation(overrides?: { patchedValue?: boolean }) {
  mockedApiFetch.mockImplementation((path: string, options?: RequestInit) => {
    if (path === "/admin/system") return Promise.resolve(SYSTEM_INFO);
    if (path === "/admin/settings" && options?.method === "PATCH") {
      const body = JSON.parse(options.body as string);
      return Promise.resolve({
        ...BEHAVIOR_SETTINGS[0],
        value: overrides?.patchedValue ?? body.value,
        updated_by: 1,
        updated_at: "2026-07-21T00:00:00Z",
      });
    }
    if (path === "/admin/settings") return Promise.resolve(BEHAVIOR_SETTINGS);
    return Promise.reject(new Error(`unexpected fetch: ${path}`));
  });
}

describe("AdminSettingsPage", () => {
  it("renders providers as read-only and the behavior catalog with a switch for the editable entry", async () => {
    mockFetchImplementation();
    renderPage(<AdminSettingsPage />);

    expect(await screen.findAllByText("openai")).toHaveLength(2);
    expect(screen.getByText("openwa")).toBeInTheDocument();

    const toggle = screen.getByRole("switch", { name: "auto_reply_enabled" });
    expect(toggle).toHaveAttribute("aria-checked", "true");

    // jobs_enabled and environment are read-only -- rendered as badges, not switches.
    expect(screen.queryByRole("switch", { name: "jobs_enabled" })).not.toBeInTheDocument();
    expect(screen.getByText("production")).toBeInTheDocument();
  });

  it("toggling the switch calls PATCH with the new value and updates immediately", async () => {
    mockFetchImplementation({ patchedValue: false });
    renderPage(<AdminSettingsPage />);

    const toggle = await screen.findByRole("switch", { name: "auto_reply_enabled" });
    expect(toggle).toHaveAttribute("aria-checked", "true");

    await userEvent.click(toggle);

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith(
        "/admin/settings",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ key: "auto_reply_enabled", value: false }),
        })
      )
    );
  });
});
