import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import TaskForm from "@/components/tasks/TaskForm";

function stubFetch(response: { ok: boolean; status?: number; json: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

describe("TaskForm", () => {
  it("renders the title, priority, due date and submit button", () => {
    render(<TaskForm onCreated={vi.fn()} />);

    expect(screen.getByRole("form", { name: "Nova tarefa" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Título da tarefa")).toBeInTheDocument();
    expect(screen.getByLabelText("Prioridade")).toBeInTheDocument();
    expect(screen.getByLabelText("Prazo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Criar tarefa" })).toBeInTheDocument();
  });

  it("does not submit when the required title is left blank", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<TaskForm onCreated={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Criar tarefa" }));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits the filled fields (including priority and due date) and calls onCreated on success", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    const onCreated = vi.fn();
    render(<TaskForm onCreated={onCreated} />);

    await userEvent.type(screen.getByPlaceholderText("Título da tarefa"), "Pagar contas");
    await userEvent.selectOptions(screen.getByLabelText("Prioridade"), "high");
    fireEvent.change(screen.getByLabelText("Prazo"), { target: { value: "2026-08-01" } });
    await userEvent.click(screen.getByRole("button", { name: "Criar tarefa" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/tasks");
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body.title).toBe("Pagar contas");
    expect(body.priority).toBe("high");
    expect(body.due_date).toBe(new Date("2026-08-01").toISOString());
  });

  it("defaults to medium priority and omits due_date when left blank", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    render(<TaskForm onCreated={vi.fn()} />);

    await userEvent.type(screen.getByPlaceholderText("Título da tarefa"), "Tarefa simples");
    await userEvent.click(screen.getByRole("button", { name: "Criar tarefa" }));

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.priority).toBe("medium");
    expect(body.due_date).toBeNull();
  });

  it("shows the error message and does not call onCreated when the request fails", async () => {
    stubFetch({ ok: false, status: 422, json: async () => ({ detail: "Título inválido" }) });
    const onCreated = vi.fn();
    render(<TaskForm onCreated={onCreated} />);

    await userEvent.type(screen.getByPlaceholderText("Título da tarefa"), "X");
    await userEvent.click(screen.getByRole("button", { name: "Criar tarefa" }));

    expect(await screen.findByText("Título inválido")).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("disables the submit button and shows a loading label while submitting", async () => {
    let resolveFetch!: (value: unknown) => void;
    const pending = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));
    render(<TaskForm onCreated={vi.fn()} />);

    await userEvent.type(screen.getByPlaceholderText("Título da tarefa"), "Tarefa X");
    fireEvent.click(screen.getByRole("button", { name: "Criar tarefa" }));

    const submitButton = await screen.findByRole("button", { name: "Criando…" });
    expect(submitButton).toBeDisabled();

    resolveFetch({ ok: true, json: async () => ({ id: 1 }) });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Criar tarefa" })).not.toBeDisabled()
    );
  });

  it("resets the form fields after a successful submit", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    render(<TaskForm onCreated={vi.fn()} />);

    const titleInput = screen.getByPlaceholderText("Título da tarefa") as HTMLInputElement;
    await userEvent.type(titleInput, "Tarefa a ser limpa");
    await userEvent.selectOptions(screen.getByLabelText("Prioridade"), "high");
    await userEvent.click(screen.getByRole("button", { name: "Criar tarefa" }));

    await waitFor(() => expect(titleInput.value).toBe(""));
    expect((screen.getByLabelText("Prioridade") as HTMLSelectElement).value).toBe("medium");
  });
});
