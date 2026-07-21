import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import NoteForm from "@/components/notes/NoteForm";

function stubFetch(response: { ok: boolean; status?: number; json: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

describe("NoteForm", () => {
  it("submits title/content/tags/pinned and calls onSaved on success", async () => {
    stubFetch({ ok: true, status: 201, json: async () => ({ id: 1 }) });
    const onSaved = vi.fn();
    render(<NoteForm onSaved={onSaved} />);

    await userEvent.type(screen.getByPlaceholderText("Título da nota"), "Ideia");
    await userEvent.type(
      screen.getByPlaceholderText("Conteúdo (Ctrl+Enter para salvar)"),
      "Automatizar avisos"
    );
    await userEvent.type(
      screen.getByPlaceholderText("Tags separadas por vírgula (opcional)"),
      "igreja, urgente"
    );
    await userEvent.click(screen.getByLabelText("Fixar no topo"));
    await userEvent.click(screen.getByRole("button", { name: "Criar nota" }));

    expect(onSaved).toHaveBeenCalledTimes(1);
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/notes");
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body).toEqual({
      title: "Ideia",
      content: "Automatizar avisos",
      tags: ["igreja", "urgente"],
      pinned: true,
    });
  });

  it("shows an error message and does not call onSaved when the request fails", async () => {
    stubFetch({ ok: false, status: 422, json: async () => ({ detail: "Título inválido" }) });
    const onSaved = vi.fn();
    render(<NoteForm onSaved={onSaved} />);

    await userEvent.type(screen.getByPlaceholderText("Título da nota"), "X");
    await userEvent.click(screen.getByRole("button", { name: "Criar nota" }));

    expect(await screen.findByText("Título inválido")).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("submits on Ctrl+Enter from the content field", async () => {
    stubFetch({ ok: true, status: 201, json: async () => ({ id: 1 }) });
    const onSaved = vi.fn();
    render(<NoteForm onSaved={onSaved} />);

    await userEvent.type(screen.getByPlaceholderText("Título da nota"), "Rápida");
    const contentField = screen.getByPlaceholderText("Conteúdo (Ctrl+Enter para salvar)");
    await userEvent.click(contentField);
    await userEvent.keyboard("{Control>}{Enter}{/Control}");

    expect(onSaved).toHaveBeenCalledTimes(1);
  });

  describe("edit mode", () => {
    const note = {
      id: 7,
      title: "Nota existente",
      content: "Conteúdo existente",
      tags: ["a", "b"],
      pinned: true,
    };

    it("prefills fields from the note prop", () => {
      stubFetch({ ok: true, json: async () => ({}) });
      render(<NoteForm note={note} onSaved={vi.fn()} />);

      expect(screen.getByPlaceholderText("Título da nota")).toHaveValue("Nota existente");
      expect(screen.getByPlaceholderText("Conteúdo (Ctrl+Enter para salvar)")).toHaveValue(
        "Conteúdo existente"
      );
      expect(screen.getByPlaceholderText("Tags separadas por vírgula (opcional)")).toHaveValue(
        "a, b"
      );
      expect(screen.getByLabelText("Fixar no topo")).toBeChecked();
      expect(screen.getByRole("form", { name: "Editar nota" })).toBeInTheDocument();
    });

    it("PATCHes the note endpoint on submit", async () => {
      stubFetch({ ok: true, json: async () => ({}) });
      const onSaved = vi.fn();
      render(<NoteForm note={note} onSaved={onSaved} />);

      await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

      const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toContain("/notes/7");
      expect(options.method).toBe("PATCH");
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
  });
});
