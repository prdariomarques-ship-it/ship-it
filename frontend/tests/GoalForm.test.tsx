import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import GoalForm from "@/components/goals/GoalForm";

function stubFetch(response: { ok: boolean; status?: number; json: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

describe("GoalForm", () => {
  it("submits the filled fields and calls onCreated on success", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    const onCreated = vi.fn();
    render(<GoalForm onCreated={onCreated} />);

    await userEvent.type(screen.getByPlaceholderText("Título da meta"), "Aprender violão");
    await userEvent.selectOptions(screen.getByLabelText("Prioridade"), "high");
    await userEvent.click(screen.getByRole("button", { name: "Criar meta" }));

    expect(onCreated).toHaveBeenCalledTimes(1);
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/goals");
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body.title).toBe("Aprender violão");
    expect(body.priority).toBe("high");
    expect(body.requires_approval).toBe(false);
  });

  it("sends requires_approval true when the checkbox is checked", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    render(<GoalForm onCreated={vi.fn()} />);

    await userEvent.type(screen.getByPlaceholderText("Título da meta"), "Meta sensível");
    await userEvent.click(
      screen.getByLabelText("Exigir aprovação de um admin antes de começar")
    );
    await userEvent.click(screen.getByRole("button", { name: "Criar meta" }));

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.requires_approval).toBe(true);
  });

  it("shows the error message and does not call onCreated when the request fails", async () => {
    stubFetch({ ok: false, status: 422, json: async () => ({ detail: "Título inválido" }) });
    const onCreated = vi.fn();
    render(<GoalForm onCreated={onCreated} />);

    await userEvent.type(screen.getByPlaceholderText("Título da meta"), "X");
    await userEvent.click(screen.getByRole("button", { name: "Criar meta" }));

    expect(await screen.findByText("Título inválido")).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("resets the form fields after a successful submit", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    render(<GoalForm onCreated={vi.fn()} />);

    const titleInput = screen.getByPlaceholderText("Título da meta") as HTMLInputElement;
    await userEvent.type(titleInput, "Alguma meta");
    await userEvent.click(screen.getByRole("button", { name: "Criar meta" }));

    expect(titleInput.value).toBe("");
  });

  it("omits recurrence_interval_days when left blank", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    render(<GoalForm onCreated={vi.fn()} />);

    await userEvent.type(screen.getByPlaceholderText("Título da meta"), "X");
    await userEvent.click(screen.getByRole("button", { name: "Criar meta" }));

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.recurrence_interval_days).toBeNull();
  });

  describe("edit mode", () => {
    const goal = {
      id: 7,
      title: "Meta existente",
      description: "Descrição existente",
      priority: "medium",
      deadline: "2026-12-31T00:00:00Z",
    };

    it("prefills fields from the goal prop", () => {
      stubFetch({ ok: true, json: async () => ({}) });
      render(<GoalForm goal={goal} onCreated={vi.fn()} />);

      expect(screen.getByPlaceholderText("Título da meta")).toHaveValue("Meta existente");
      expect(screen.getByPlaceholderText("Descrição (opcional)")).toHaveValue(
        "Descrição existente"
      );
      expect(screen.getByRole("form", { name: "Editar meta" })).toBeInTheDocument();
    });

    it("hides recurrence and approval fields", () => {
      stubFetch({ ok: true, json: async () => ({}) });
      render(<GoalForm goal={goal} onCreated={vi.fn()} />);

      expect(
        screen.queryByPlaceholderText("Repetir a cada N dias (opcional)")
      ).not.toBeInTheDocument();
      expect(
        screen.queryByLabelText("Exigir aprovação de um admin antes de começar")
      ).not.toBeInTheDocument();
    });

    it("PATCHes the goal endpoint with the edited fields on submit", async () => {
      stubFetch({ ok: true, json: async () => ({}) });
      const onCreated = vi.fn();
      render(<GoalForm goal={goal} onCreated={onCreated} />);

      const titleInput = screen.getByPlaceholderText("Título da meta");
      await userEvent.clear(titleInput);
      await userEvent.type(titleInput, "Meta editada");
      await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

      expect(onCreated).toHaveBeenCalledTimes(1);
      const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toContain("/goals/7");
      expect(options.method).toBe("PATCH");
      const body = JSON.parse(options.body);
      expect(body.title).toBe("Meta editada");
      expect(body.recurrence_interval_days).toBeUndefined();
      expect(body.requires_approval).toBeUndefined();
    });
  });
});
