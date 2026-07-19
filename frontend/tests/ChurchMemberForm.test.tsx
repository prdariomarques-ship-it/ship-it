import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ChurchMemberForm from "@/components/church/ChurchMemberForm";

function stubFetch(response: { ok: boolean; status?: number; json: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

describe("ChurchMemberForm", () => {
  it("renders the name, phone, role and submit button", () => {
    render(<ChurchMemberForm onCreated={vi.fn()} />);

    expect(screen.getByRole("form", { name: "Novo membro" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Nome")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Telefone (opcional)")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Função no ministério (opcional)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Criar membro" })).toBeInTheDocument();
  });

  it("does not submit when the required name is left blank", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<ChurchMemberForm onCreated={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Criar membro" }));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits the filled fields and calls onCreated on success", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    const onCreated = vi.fn();
    render(<ChurchMemberForm onCreated={onCreated} />);

    await userEvent.type(screen.getByPlaceholderText("Nome"), "João Pereira");
    await userEvent.type(screen.getByPlaceholderText("Telefone (opcional)"), "11977776666");
    await userEvent.type(
      screen.getByPlaceholderText("Função no ministério (opcional)"),
      "Louvor"
    );
    await userEvent.click(screen.getByRole("button", { name: "Criar membro" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/church/members");
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body.name).toBe("João Pereira");
    expect(body.phone).toBe("11977776666");
    expect(body.role).toBe("Louvor");
  });

  it("omits phone and role as null when left blank", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    render(<ChurchMemberForm onCreated={vi.fn()} />);

    await userEvent.type(screen.getByPlaceholderText("Nome"), "Membro sem função");
    await userEvent.click(screen.getByRole("button", { name: "Criar membro" }));

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.phone).toBeNull();
    expect(body.role).toBeNull();
  });

  it("shows the error message and does not call onCreated when the request fails", async () => {
    stubFetch({ ok: false, status: 422, json: async () => ({ detail: "Nome inválido" }) });
    const onCreated = vi.fn();
    render(<ChurchMemberForm onCreated={onCreated} />);

    await userEvent.type(screen.getByPlaceholderText("Nome"), "X");
    await userEvent.click(screen.getByRole("button", { name: "Criar membro" }));

    expect(await screen.findByText("Nome inválido")).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("disables the submit button and shows a loading label while submitting", async () => {
    let resolveFetch!: (value: unknown) => void;
    const pending = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));
    render(<ChurchMemberForm onCreated={vi.fn()} />);

    await userEvent.type(screen.getByPlaceholderText("Nome"), "Membro X");
    fireEvent.click(screen.getByRole("button", { name: "Criar membro" }));

    const submitButton = await screen.findByRole("button", { name: "Criando…" });
    expect(submitButton).toBeDisabled();

    resolveFetch({ ok: true, json: async () => ({ id: 1 }) });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Criar membro" })).not.toBeDisabled()
    );
  });

  it("resets the form fields after a successful submit", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    render(<ChurchMemberForm onCreated={vi.fn()} />);

    const nameInput = screen.getByPlaceholderText("Nome") as HTMLInputElement;
    const roleInput = screen.getByPlaceholderText(
      "Função no ministério (opcional)"
    ) as HTMLInputElement;
    await userEvent.type(nameInput, "Membro a ser limpo");
    await userEvent.type(roleInput, "Diaconia");
    await userEvent.click(screen.getByRole("button", { name: "Criar membro" }));

    await waitFor(() => expect(nameInput.value).toBe(""));
    expect(roleInput.value).toBe("");
  });
});
