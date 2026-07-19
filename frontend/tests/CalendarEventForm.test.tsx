import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import CalendarEventForm from "@/components/calendar/CalendarEventForm";

function stubFetch(response: { ok: boolean; status?: number; json: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

describe("CalendarEventForm", () => {
  it("renders the title, start/end and submit button", () => {
    render(<CalendarEventForm onCreated={vi.fn()} />);

    expect(screen.getByRole("form", { name: "Novo evento" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Título do evento")).toBeInTheDocument();
    expect(screen.getByLabelText("Início")).toBeInTheDocument();
    expect(screen.getByLabelText("Fim")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Criar evento" })).toBeInTheDocument();
  });

  it("does not submit when the required title is left blank", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<CalendarEventForm onCreated={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Início"), {
      target: { value: "2026-08-01T10:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Criar evento" }));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits the filled fields and calls onCreated on success", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    const onCreated = vi.fn();
    render(<CalendarEventForm onCreated={onCreated} />);

    await userEvent.type(screen.getByPlaceholderText("Título do evento"), "Reunião de equipe");
    await userEvent.type(screen.getByPlaceholderText("Local (opcional)"), "Sala 2");
    fireEvent.change(screen.getByLabelText("Início"), {
      target: { value: "2026-08-01T10:00" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Criar evento" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/calendar");
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body.title).toBe("Reunião de equipe");
    expect(body.location).toBe("Sala 2");
    expect(body.starts_at).toBe(new Date("2026-08-01T10:00").toISOString());
    expect(body.ends_at).toBeNull();
  });

  it("shows the error message and does not call onCreated when the request fails", async () => {
    stubFetch({ ok: false, status: 422, json: async () => ({ detail: "Horário inválido" }) });
    const onCreated = vi.fn();
    render(<CalendarEventForm onCreated={onCreated} />);

    await userEvent.type(screen.getByPlaceholderText("Título do evento"), "Evento X");
    fireEvent.change(screen.getByLabelText("Início"), {
      target: { value: "2026-08-01T10:00" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Criar evento" }));

    expect(await screen.findByText("Horário inválido")).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("disables the submit button and shows a loading label while submitting", async () => {
    let resolveFetch!: (value: unknown) => void;
    const pending = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));
    render(<CalendarEventForm onCreated={vi.fn()} />);

    await userEvent.type(screen.getByPlaceholderText("Título do evento"), "Evento X");
    fireEvent.change(screen.getByLabelText("Início"), {
      target: { value: "2026-08-01T10:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Criar evento" }));

    const submitButton = await screen.findByRole("button", { name: "Criando…" });
    expect(submitButton).toBeDisabled();

    resolveFetch({ ok: true, json: async () => ({ id: 1 }) });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Criar evento" })).not.toBeDisabled()
    );
  });

  it("resets the form fields after a successful submit", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    render(<CalendarEventForm onCreated={vi.fn()} />);

    const titleInput = screen.getByPlaceholderText("Título do evento") as HTMLInputElement;
    await userEvent.type(titleInput, "Evento a ser limpo");
    fireEvent.change(screen.getByLabelText("Início"), {
      target: { value: "2026-08-01T10:00" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Criar evento" }));

    await waitFor(() => expect(titleInput.value).toBe(""));
  });
});
