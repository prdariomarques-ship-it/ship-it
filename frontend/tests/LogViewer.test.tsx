import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LogViewer } from "@/components/admin/LogViewer";
import type { AdminLogEntry } from "@/lib/admin-types";

const logs: AdminLogEntry[] = [
  {
    id: 1,
    level: "error",
    source: "agent:store",
    message: "Falha ao consultar estoque",
    payload: { error: "timeout" },
    created_at: new Date().toISOString(),
  },
];

describe("LogViewer", () => {
  it("shows an empty state when there are no logs", () => {
    render(<LogViewer logs={[]} level={undefined} onLevelChange={vi.fn()} search="" onSearchChange={vi.fn()} />);
    expect(screen.getByText("Nenhum log encontrado")).toBeInTheDocument();
  });

  it("renders log rows with level and source", () => {
    render(<LogViewer logs={logs} level={undefined} onLevelChange={vi.fn()} search="" onSearchChange={vi.fn()} />);
    expect(screen.getByText("Falha ao consultar estoque")).toBeInTheDocument();
    expect(screen.getByText("[agent:store]")).toBeInTheDocument();
  });

  it("calls onLevelChange when a level chip is clicked", async () => {
    const onLevelChange = vi.fn();
    render(<LogViewer logs={logs} level={undefined} onLevelChange={onLevelChange} search="" onSearchChange={vi.fn()} />);
    // Both the filter chip and the seeded log row's own level badge render
    // the text "error" (chips are level names, the log fixture is an error
    // log) — the filter chip is the first "error" in DOM order.
    await userEvent.click(screen.getAllByText("error")[0]);
    expect(onLevelChange).toHaveBeenCalledWith("error");
  });

  it("calls onSearchChange as the user types", async () => {
    const onSearchChange = vi.fn();
    render(<LogViewer logs={logs} level={undefined} onLevelChange={vi.fn()} search="" onSearchChange={onSearchChange} />);
    await userEvent.type(screen.getByPlaceholderText("Buscar na mensagem…"), "x");
    expect(onSearchChange).toHaveBeenCalledWith("x");
  });

  it("expands payload details on row click", async () => {
    render(<LogViewer logs={logs} level={undefined} onLevelChange={vi.fn()} search="" onSearchChange={vi.fn()} />);
    await userEvent.click(screen.getByText("Falha ao consultar estoque"));
    expect(await screen.findByText(/"error": "timeout"/)).toBeInTheDocument();
  });

  it("clicking 'todos' clears the level filter", async () => {
    const onLevelChange = vi.fn();
    render(<LogViewer logs={logs} level="error" onLevelChange={onLevelChange} search="" onSearchChange={vi.fn()} />);
    await userEvent.click(screen.getByText("todos"));
    expect(onLevelChange).toHaveBeenCalledWith(undefined);
  });

  it("exports the currently loaded logs as a downloaded JSON file", async () => {
    const createObjectURL = vi.fn(() => "blob:mock-url");
    const revokeObjectURL = vi.fn();
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<LogViewer logs={logs} level={undefined} onLevelChange={vi.fn()} search="" onSearchChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /exportar/i }));

    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(clickSpy).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");

    clickSpy.mockRestore();
  });
});
