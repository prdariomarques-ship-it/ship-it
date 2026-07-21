import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useApi", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/hooks/useApi";
import AdminWhatsAppPage from "@/app/admin/whatsapp/page";
import { renderWithQueryClient } from "./test-utils";

const mockedApiFetch = vi.mocked(apiFetch);

const BASE_STATUS = {
  provider: "openwa",
  connected: true,
  detail: "CONNECTED",
  queue_depth: 0,
  messages_sent: 10,
  messages_received: 5,
};

describe("AdminWhatsAppPage", () => {
  it("shows a QR link when qr_page_url is present", async () => {
    mockedApiFetch.mockResolvedValue({
      ...BASE_STATUS,
      qr_page_url: "http://192.168.1.10:8002",
    });
    renderWithQueryClient(<AdminWhatsAppPage />);

    const link = await screen.findByRole("link", { name: "Ver QR Code / reconectar" });
    expect(link).toHaveAttribute("href", "http://192.168.1.10:8002");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("shows a fallback message when qr_page_url is null", async () => {
    mockedApiFetch.mockResolvedValue({ ...BASE_STATUS, qr_page_url: null });
    renderWithQueryClient(<AdminWhatsAppPage />);

    await waitFor(() =>
      expect(screen.getByText(/QR Code não disponível/)).toBeInTheDocument()
    );
    expect(screen.queryByRole("link", { name: "Ver QR Code / reconectar" })).not.toBeInTheDocument();
  });
});
