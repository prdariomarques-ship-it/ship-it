import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import StoreCustomerForm from "@/components/store/StoreCustomerForm";

function stubFetch(response: { ok: boolean; status?: number; json: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

describe("StoreCustomerForm", () => {
  it("renders the name, phone, email and submit button", () => {
    render(<StoreCustomerForm onCreated={vi.fn()} />);

    expect(screen.getByRole("form", { name: "Novo cliente" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Nome")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Telefone (opcional)")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("E-mail (opcional)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Criar cliente" })).toBeInTheDocument();
  });

  it("does not submit when the required name is left blank", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<StoreCustomerForm onCreated={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Criar cliente" }));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits the filled fields and calls onCreated on success", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    const onCreated = vi.fn();
    render(<StoreCustomerForm onCreated={onCreated} />);

    await userEvent.type(screen.getByPlaceholderText("Nome"), "Maria Silva");
    await userEvent.type(screen.getByPlaceholderText("Telefone (opcional)"), "11999990000");
    await userEvent.type(screen.getByPlaceholderText("E-mail (opcional)"), "maria@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Criar cliente" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/store/customers");
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body.name).toBe("Maria Silva");
    expect(body.phone).toBe("11999990000");
    expect(body.email).toBe("maria@example.com");
  });

  it("omits phone and email as null when left blank", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    render(<StoreCustomerForm onCreated={vi.fn()} />);

    await userEvent.type(screen.getByPlaceholderText("Nome"), "Cliente sem contato");
    await userEvent.click(screen.getByRole("button", { name: "Criar cliente" }));

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.phone).toBeNull();
    expect(body.email).toBeNull();
  });

  it("shows the error message and does not call onCreated when the request fails", async () => {
    stubFetch({ ok: false, status: 422, json: async () => ({ detail: "Nome inválido" }) });
    const onCreated = vi.fn();
    render(<StoreCustomerForm onCreated={onCreated} />);

    await userEvent.type(screen.getByPlaceholderText("Nome"), "X");
    await userEvent.click(screen.getByRole("button", { name: "Criar cliente" }));

    expect(await screen.findByText("Nome inválido")).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("disables the submit button and shows a loading label while submitting", async () => {
    let resolveFetch!: (value: unknown) => void;
    const pending = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));
    render(<StoreCustomerForm onCreated={vi.fn()} />);

    await userEvent.type(screen.getByPlaceholderText("Nome"), "Cliente X");
    fireEvent.click(screen.getByRole("button", { name: "Criar cliente" }));

    const submitButton = await screen.findByRole("button", { name: "Criando…" });
    expect(submitButton).toBeDisabled();

    resolveFetch({ ok: true, json: async () => ({ id: 1 }) });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Criar cliente" })).not.toBeDisabled()
    );
  });

  it("resets the form fields after a successful submit", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    render(<StoreCustomerForm onCreated={vi.fn()} />);

    const nameInput = screen.getByPlaceholderText("Nome") as HTMLInputElement;
    const phoneInput = screen.getByPlaceholderText("Telefone (opcional)") as HTMLInputElement;
    await userEvent.type(nameInput, "Cliente a ser limpo");
    await userEvent.type(phoneInput, "11988887777");
    await userEvent.click(screen.getByRole("button", { name: "Criar cliente" }));

    await waitFor(() => expect(nameInput.value).toBe(""));
    expect(phoneInput.value).toBe("");
  });
});
