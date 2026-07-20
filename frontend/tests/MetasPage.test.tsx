import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import MetasPage from "@/app/(dashboard)/metas/page";

const GOAL = {
  id: 1,
  title: "Aprender violão",
  status: "awaiting_approval",
  priority: "high",
  deadline: null,
  progress_percent: 0,
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

describe("MetasPage", () => {
  it("renders the goal list with a status badge", async () => {
    mockFetchByPath({ "/goals": [GOAL], "/auth/me": { role: "user" } });
    render(<MetasPage />);

    expect(await screen.findByText("Aprender violão")).toBeInTheDocument();
    expect(screen.getByText("Aguardando aprovação")).toBeInTheDocument();
  });

  it("shows the create form when 'Nova meta' is clicked", async () => {
    mockFetchByPath({ "/goals": [], "/auth/me": { role: "user" } });
    render(<MetasPage />);

    await waitFor(() => expect(screen.getByText("Nenhuma meta cadastrada.")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Nova meta" }));

    expect(screen.getByRole("form", { name: "Nova meta" })).toBeInTheDocument();
  });

  it("does not show an approve button for a non-admin user", async () => {
    mockFetchByPath({ "/goals": [GOAL], "/auth/me": { role: "user" } });
    render(<MetasPage />);

    await screen.findByText("Aprender violão");
    expect(screen.queryByRole("button", { name: "Aprovar" })).not.toBeInTheDocument();
  });

  it("shows an approve button for an admin on an awaiting_approval goal", async () => {
    mockFetchByPath({ "/goals": [GOAL], "/auth/me": { role: "admin" } });
    render(<MetasPage />);

    expect(await screen.findByRole("button", { name: "Aprovar" })).toBeInTheDocument();
  });

  it("does not show an approve button for a goal that isn't awaiting approval", async () => {
    mockFetchByPath({
      "/goals": [{ ...GOAL, status: "pending" }],
      "/auth/me": { role: "admin" },
    });
    render(<MetasPage />);

    await screen.findByText("Aprender violão");
    expect(screen.queryByRole("button", { name: "Aprovar" })).not.toBeInTheDocument();
  });

  it("approving a goal calls the approve endpoint and reloads the list", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/approve")) return { ok: true, status: 200, json: async () => GOAL };
      if (url.includes("/auth/me")) return { ok: true, status: 200, json: async () => ({ role: "admin" }) };
      if (url.includes("/goals")) return { ok: true, status: 200, json: async () => [GOAL] };
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MetasPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Aprovar" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/goals/1/approve"),
        expect.objectContaining({ method: "POST" })
      )
    );
  });

  it("clicking 'Editar' opens the edit form prefilled with the goal", async () => {
    mockFetchByPath({ "/goals": [GOAL], "/auth/me": { role: "user" } });
    render(<MetasPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Editar" }));

    expect(screen.getByRole("form", { name: "Editar meta" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Título da meta")).toHaveValue("Aprender violão");
  });

  it("clicking 'Detalhes' shows progress/dependencies/history for the goal", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/dependencies")) return { ok: true, status: 200, json: async () => [] };
      if (url.includes("/history")) return { ok: true, status: 200, json: async () => [] };
      if (url.includes("/auth/me")) return { ok: true, status: 200, json: async () => ({ role: "user" }) };
      if (url.includes("/goals")) return { ok: true, status: 200, json: async () => [GOAL] };
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MetasPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Detalhes" }));

    expect(await screen.findByLabelText("Progresso")).toBeInTheDocument();
  });

  it("only one row can be expanded at a time", async () => {
    mockFetchByPath({ "/goals": [GOAL], "/auth/me": { role: "user" } });
    render(<MetasPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Editar" }));
    expect(screen.getByRole("form", { name: "Editar meta" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(screen.queryByRole("form", { name: "Editar meta" })).not.toBeInTheDocument();
  });
});
