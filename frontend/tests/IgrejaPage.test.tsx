import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import IgrejaPage from "@/app/(dashboard)/igreja/page";

const MEMBER = {
  id: 1,
  name: "Pedro Alves",
  role: "louvor",
  ministries: ["louvor"],
  prayer_requests: [],
};

describe("IgrejaPage", () => {
  it("renders the member list", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [MEMBER] })
    );
    render(<IgrejaPage />);

    expect(await screen.findByText("Pedro Alves")).toBeInTheDocument();
  });

  it("shows the empty state when there are no members", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] })
    );
    render(<IgrejaPage />);

    expect(await screen.findByText("Nenhum membro cadastrado.")).toBeInTheDocument();
  });

  it("shows the create form when 'Novo membro' is clicked", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] })
    );
    render(<IgrejaPage />);

    await waitFor(() => screen.getByText("Nenhum membro cadastrado."));
    await userEvent.click(screen.getByRole("button", { name: "Novo membro" }));

    expect(screen.getByRole("form", { name: "Novo membro" })).toBeInTheDocument();
  });

  it("searches by name after debounce and requests the ?q= endpoint", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("q=alves")) {
        return { ok: true, status: 200, json: async () => [MEMBER] };
      }
      return { ok: true, status: 200, json: async () => [] };
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<IgrejaPage />);

    await waitFor(() => screen.getByText("Nenhum membro cadastrado."));
    await userEvent.type(screen.getByLabelText("Buscar membro por nome"), "alves");

    await waitFor(
      () =>
        expect(
          fetchMock.mock.calls.some(([url]) => String(url).includes("q=alves"))
        ).toBe(true),
      { timeout: 2000 }
    );
    expect(await screen.findByText("Pedro Alves")).toBeInTheDocument();
  });

  it("shows a search-specific empty message when a query has no results", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("q=")) return { ok: true, status: 200, json: async () => [] };
      return { ok: true, status: 200, json: async () => [MEMBER] };
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<IgrejaPage />);

    await screen.findByText("Pedro Alves");
    await userEvent.type(screen.getByLabelText("Buscar membro por nome"), "zzz");

    expect(
      await screen.findByText("Nenhum membro encontrado para essa busca.")
    ).toBeInTheDocument();
  });

  it("does not fire a request per keystroke (debounced)", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => [] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<IgrejaPage />);

    await waitFor(() => screen.getByText("Nenhum membro cadastrado."));
    const callsBeforeTyping = fetchMock.mock.calls.length;
    await userEvent.type(screen.getByLabelText("Buscar membro por nome"), "ab");

    // Immediately after typing, the debounce window (250ms) hasn't elapsed
    // yet -- no new fetch should have fired synchronously per keystroke.
    expect(fetchMock.mock.calls.length).toBe(callsBeforeTyping);
  });
});
