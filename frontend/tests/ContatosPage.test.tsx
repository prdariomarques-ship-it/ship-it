import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ContatosPage from "@/app/(dashboard)/contatos/page";

const CONTACT = {
  id: 1,
  name: "Ana Souza",
  phone: "+5511999990000",
  categories: ["loja"],
  last_interaction_at: "2026-01-15T10:00:00Z",
};

describe("ContatosPage", () => {
  it("renders the contact list with a link to the workspace", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [CONTACT] })
    );
    render(<ContatosPage />);

    const link = await screen.findByRole("link", { name: "Ana Souza" });
    expect(link).toHaveAttribute("href", "/contatos/1");
  });

  it("shows the empty state when there are no contacts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] })
    );
    render(<ContatosPage />);

    expect(await screen.findByText("Nenhum contato ainda.")).toBeInTheDocument();
  });

  it("searches by name after debounce and requests the ?q= endpoint", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("q=ana")) {
        return { ok: true, status: 200, json: async () => [CONTACT] };
      }
      return { ok: true, status: 200, json: async () => [] };
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ContatosPage />);

    await waitFor(() => screen.getByText("Nenhum contato ainda."));
    await userEvent.type(screen.getByLabelText("Buscar contato por nome"), "ana");

    await waitFor(
      () =>
        expect(
          fetchMock.mock.calls.some(([url]) => String(url).includes("q=ana"))
        ).toBe(true),
      { timeout: 2000 }
    );
    expect(await screen.findByRole("link", { name: "Ana Souza" })).toBeInTheDocument();
  });
});
