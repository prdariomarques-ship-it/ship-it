import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ProductForm from "@/components/store/ProductForm";

function stubFetch(response: { ok: boolean; status?: number; json: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

describe("ProductForm", () => {
  it("renders every field and the submit button", () => {
    render(<ProductForm onCreated={vi.fn()} />);

    expect(screen.getByRole("form", { name: "Novo produto" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("SKU")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Nome do produto")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Categoria (opcional, ex: tinta_latex)")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Unidade (ex: lata_18L, galao_3.6L, un)")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Preço unitário")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Estoque inicial")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Criar produto" })).toBeInTheDocument();
  });

  it("does not submit when a required field is left blank", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<ProductForm onCreated={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Criar produto" }));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits the filled fields and calls onCreated on success", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    const onCreated = vi.fn();
    render(<ProductForm onCreated={onCreated} />);

    await userEvent.type(screen.getByPlaceholderText("SKU"), "TINTA-LATEX-BR-18L");
    await userEvent.type(screen.getByPlaceholderText("Nome do produto"), "Tinta Látex Branca 18L");
    await userEvent.type(
      screen.getByPlaceholderText("Categoria (opcional, ex: tinta_latex)"),
      "tinta_latex"
    );
    await userEvent.clear(screen.getByPlaceholderText("Unidade (ex: lata_18L, galao_3.6L, un)"));
    await userEvent.type(
      screen.getByPlaceholderText("Unidade (ex: lata_18L, galao_3.6L, un)"),
      "lata_18L"
    );
    await userEvent.type(screen.getByPlaceholderText("Preço unitário"), "289.95");
    await userEvent.clear(screen.getByPlaceholderText("Estoque inicial"));
    await userEvent.type(screen.getByPlaceholderText("Estoque inicial"), "10");
    await userEvent.click(screen.getByRole("button", { name: "Criar produto" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/store/products");
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body).toEqual({
      sku: "TINTA-LATEX-BR-18L",
      name: "Tinta Látex Branca 18L",
      category: "tinta_latex",
      unit: "lata_18L",
      unit_price: "289.95",
      stock_quantity: 10,
    });
  });

  it("omits category as null when left blank", async () => {
    stubFetch({ ok: true, json: async () => ({ id: 1 }) });
    render(<ProductForm onCreated={vi.fn()} />);

    await userEvent.type(screen.getByPlaceholderText("SKU"), "ESMALTE-PT-3.6L");
    await userEvent.type(screen.getByPlaceholderText("Nome do produto"), "Esmalte Preto");
    await userEvent.type(screen.getByPlaceholderText("Preço unitário"), "59.90");
    await userEvent.click(screen.getByRole("button", { name: "Criar produto" }));

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.category).toBeNull();
  });

  it("shows the error message and does not call onCreated when the request fails", async () => {
    stubFetch({ ok: false, status: 422, json: async () => ({ detail: "SKU já existe" }) });
    const onCreated = vi.fn();
    render(<ProductForm onCreated={onCreated} />);

    await userEvent.type(screen.getByPlaceholderText("SKU"), "DUPLICADO");
    await userEvent.type(screen.getByPlaceholderText("Nome do produto"), "Produto X");
    await userEvent.type(screen.getByPlaceholderText("Preço unitário"), "10.00");
    await userEvent.click(screen.getByRole("button", { name: "Criar produto" }));

    expect(await screen.findByText("SKU já existe")).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
  });
});
