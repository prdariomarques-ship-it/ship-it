import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ProductsPanel from "@/components/store/ProductsPanel";

const PRODUCTS = [
  {
    id: 1,
    sku: "TINTA-LATEX-BR-18L",
    name: "Tinta Látex Branca 18L",
    category: "tinta_latex",
    unit: "lata_18L",
    unit_price: "289.90",
    stock_quantity: 12,
    active: true,
  },
  {
    id: 2,
    sku: "ESMALTE-PT-3.6L",
    name: "Esmalte Preto 3.6L",
    category: null,
    unit: "galao_3.6L",
    unit_price: "59.90",
    stock_quantity: 3,
    active: false,
  },
];

function mockFetchByPath(byPath: Record<string, unknown>) {
  return vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    const match = Object.keys(byPath).find((path) => url.includes(path));
    if (!match) throw new Error(`Unexpected fetch to ${url}`);
    return { ok: true, status: 200, json: async () => byPath[match] };
  });
}

describe("ProductsPanel", () => {
  it("lists products with low-stock and status badges", async () => {
    vi.stubGlobal("fetch", mockFetchByPath({ "/store/products": PRODUCTS }));
    render(<ProductsPanel />);

    const row1 = (await screen.findByText("Tinta Látex Branca 18L")).closest("tr") as HTMLElement;
    expect(within(row1).getByText("R$ 289.90")).toBeInTheDocument();
    expect(within(row1).getByText("Ativo")).toBeInTheDocument();
    expect(within(row1).queryByText("estoque baixo")).not.toBeInTheDocument();

    const row2 = screen.getByText("Esmalte Preto 3.6L").closest("tr") as HTMLElement;
    expect(within(row2).getByText("Inativo")).toBeInTheDocument();
    expect(within(row2).getByText("estoque baixo")).toBeInTheDocument();
  });

  it("shows an empty message when there are no products", async () => {
    vi.stubGlobal("fetch", mockFetchByPath({ "/store/products": [] }));
    render(<ProductsPanel />);

    expect(await screen.findByText("Nenhum produto cadastrado.")).toBeInTheDocument();
  });

  it("toggles the creation form and reloads the list after a product is created", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.includes("/store/products") && method === "POST") {
        return { ok: true, status: 201, json: async () => ({ id: 3 }) };
      }
      if (url.includes("/store/products") && method === "GET") {
        return { ok: true, status: 200, json: async () => PRODUCTS };
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ProductsPanel />);

    await screen.findByText("Tinta Látex Branca 18L");
    await userEvent.click(screen.getByRole("button", { name: "Novo produto" }));
    expect(screen.getByRole("form", { name: "Novo produto" })).toBeInTheDocument();

    await userEvent.type(screen.getByPlaceholderText("SKU"), "VERNIZ-MARITIMO-3.6L");
    await userEvent.type(screen.getByPlaceholderText("Nome do produto"), "Verniz Marítimo");
    await userEvent.type(screen.getByPlaceholderText("Preço unitário"), "89.90");
    await userEvent.click(screen.getByRole("button", { name: "Criar produto" }));

    await waitFor(() =>
      expect(screen.queryByRole("form", { name: "Novo produto" })).not.toBeInTheDocument()
    );
    expect(
      fetchMock.mock.calls.filter(
        ([u, i]) =>
          String(u).includes("/store/products") &&
          ((i as RequestInit | undefined)?.method ?? "GET") === "GET"
      ).length
    ).toBeGreaterThanOrEqual(2);
  });

  it("edits a product's price, stock and status and saves via PATCH", async () => {
    const fetchMock = mockFetchByPath({ "/store/products": PRODUCTS });
    vi.stubGlobal("fetch", fetchMock);
    render(<ProductsPanel />);

    await screen.findByText("Tinta Látex Branca 18L");
    const row1 = screen.getByText("Tinta Látex Branca 18L").closest("tr") as HTMLElement;
    await userEvent.click(within(row1).getByRole("button", { name: "Editar" }));

    const priceInput = screen.getByLabelText("Preço de Tinta Látex Branca 18L");
    const stockInput = screen.getByLabelText("Estoque de Tinta Látex Branca 18L");
    const activeCheckbox = screen.getByLabelText("Ativo: Tinta Látex Branca 18L");

    await userEvent.clear(priceInput);
    await userEvent.type(priceInput, "299.95");
    await userEvent.clear(stockInput);
    await userEvent.type(stockInput, "20");
    await userEvent.click(activeCheckbox);

    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/store/products/1"),
        expect.objectContaining({ method: "PATCH" })
      )
    );
    const call = fetchMock.mock.calls.find(
      ([url, options]) =>
        String(url).includes("/store/products/1") &&
        (options as RequestInit | undefined)?.method === "PATCH"
    );
    expect(JSON.parse((call as [unknown, RequestInit])[1].body as string)).toEqual({
      unit_price: "299.95",
      stock_quantity: 20,
      active: false,
    });
    await waitFor(() =>
      expect(screen.queryByLabelText("Preço de Tinta Látex Branca 18L")).not.toBeInTheDocument()
    );
  });

  it("discards edits when Cancelar is clicked", async () => {
    const fetchMock = mockFetchByPath({ "/store/products": PRODUCTS });
    vi.stubGlobal("fetch", fetchMock);
    render(<ProductsPanel />);

    await screen.findByText("Tinta Látex Branca 18L");
    const row1 = screen.getByText("Tinta Látex Branca 18L").closest("tr") as HTMLElement;
    await userEvent.click(within(row1).getByRole("button", { name: "Editar" }));

    const priceInput = screen.getByLabelText("Preço de Tinta Látex Branca 18L");
    await userEvent.clear(priceInput);
    await userEvent.type(priceInput, "1.00");
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByLabelText("Preço de Tinta Látex Branca 18L")).not.toBeInTheDocument();
    expect(within(row1).getByText("R$ 289.90")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, options]) => (options as RequestInit | undefined)?.method === "PATCH")).toBe(
      false
    );
  });
});
