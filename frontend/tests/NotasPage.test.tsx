import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import NotasPage from "@/app/(dashboard)/notas/page";

const NOTE = {
  id: 1,
  title: "Ideia de automação",
  content: "Automatizar avisos do culto",
  tags: ["igreja"],
  pinned: false,
  archived: false,
};

function mockFetchByPath(byPath: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const match = Object.keys(byPath).find((path) => url.includes(path));
      if (!match) throw new Error(`Unexpected fetch to ${url}`);
      return { ok: true, status: 200, json: async () => byPath[match] };
    })
  );
}

describe("NotasPage", () => {
  it("renders the note list", async () => {
    mockFetchByPath({ "/notes": [NOTE] });
    render(<NotasPage />);

    expect(await screen.findByText("Ideia de automação")).toBeInTheDocument();
    expect(screen.getByText("Automatizar avisos do culto")).toBeInTheDocument();
  });

  it("shows the empty state when there are no notes", async () => {
    mockFetchByPath({ "/notes": [] });
    render(<NotasPage />);

    expect(await screen.findByText("Nenhuma nota cadastrada.")).toBeInTheDocument();
  });

  it("shows the create form when 'Nova nota' is clicked", async () => {
    mockFetchByPath({ "/notes": [] });
    render(<NotasPage />);

    await waitFor(() => screen.getByText("Nenhuma nota cadastrada."));
    await userEvent.click(screen.getByRole("button", { name: "Nova nota" }));

    expect(screen.getByRole("form", { name: "Nova nota" })).toBeInTheDocument();
  });

  it("shows a pinned marker and archived badge when applicable", async () => {
    mockFetchByPath({
      "/notes": [{ ...NOTE, pinned: true, archived: true }],
    });
    render(<NotasPage />);

    expect(await screen.findByLabelText("Fixada")).toBeInTheDocument();
    expect(screen.getByText("arquivada")).toBeInTheDocument();
  });

  it("searches by query after debounce and requests the right endpoint", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("q=or")) {
        return { ok: true, status: 200, json: async () => [NOTE] };
      }
      return { ok: true, status: 200, json: async () => [] };
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<NotasPage />);

    await waitFor(() => screen.getByText("Nenhuma nota cadastrada."));
    await userEvent.type(screen.getByLabelText("Buscar notas"), "orçamento");

    await waitFor(
      () =>
        expect(
          fetchMock.mock.calls.some(([url]) => String(url).includes("q=or"))
        ).toBe(true),
      { timeout: 2000 }
    );
    expect(await screen.findByText("Ideia de automação")).toBeInTheDocument();
  });

  it("requests include_archived=true when the checkbox is toggled", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => ({
      ok: true,
      status: 200,
      json: async () => [],
    }));
    vi.stubGlobal("fetch", fetchMock);
    render(<NotasPage />);

    await waitFor(() => screen.getByText("Nenhuma nota cadastrada."));
    await userEvent.click(screen.getByLabelText("Mostrar arquivadas"));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).includes("include_archived=true")
        )
      ).toBe(true)
    );
  });

  it("deletes a note and reloads the list", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      if (options?.method === "DELETE") {
        return { ok: true, status: 204, json: async () => ({}) };
      }
      if (url.includes("/notes")) {
        return { ok: true, status: 200, json: async () => [NOTE] };
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<NotasPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Apagar" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/notes/1"),
        expect.objectContaining({ method: "DELETE" })
      )
    );
  });
});
