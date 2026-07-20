import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useApi", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/hooks/useApi";
import { MemorySearch } from "@/components/admin/MemorySearch";
import { renderWithQueryClient } from "./test-utils";

const mockedApiFetch = vi.mocked(apiFetch);

describe("MemorySearch", () => {
  it("does not search until the form is submitted", () => {
    renderWithQueryClient(<MemorySearch />);
    expect(mockedApiFetch).not.toHaveBeenCalled();
  });

  it("searches and renders results on submit", async () => {
    mockedApiFetch.mockResolvedValue([
      { content: "Prefere contato por WhatsApp", source: "contact:42", contact_id: 42, score: 0.87 },
    ]);
    renderWithQueryClient(<MemorySearch />);

    await userEvent.type(screen.getByLabelText("Busca semântica"), "contato interessado");
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));

    expect(await screen.findByText("Prefere contato por WhatsApp")).toBeInTheDocument();
    expect(screen.getByText("Contato #42")).toBeInTheDocument();
    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("/memory/search?q=contato")
      )
    );
  });

  it("shows an empty state when the search has no results", async () => {
    mockedApiFetch.mockResolvedValue([]);
    renderWithQueryClient(<MemorySearch />);

    await userEvent.type(screen.getByLabelText("Busca semântica"), "algo raro");
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));

    expect(await screen.findByText("Nenhum resultado")).toBeInTheDocument();
  });

  it("shows an error state when the search fails", async () => {
    mockedApiFetch.mockRejectedValue(new Error("Vector store unavailable"));
    renderWithQueryClient(<MemorySearch />);

    await userEvent.type(screen.getByLabelText("Busca semântica"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));

    expect(await screen.findByText("Vector store unavailable")).toBeInTheDocument();
  });

  it("disables the search button while the query is empty", () => {
    renderWithQueryClient(<MemorySearch />);
    expect(screen.getByRole("button", { name: "Buscar" })).toBeDisabled();
  });
});
