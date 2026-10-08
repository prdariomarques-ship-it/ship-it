import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import MercadoBrasilPage from "@/app/(dashboard)/mercado-brasil/page";
import MercadoGlobalPage from "@/app/(dashboard)/mercado-global/page";

describe("MercadoBrasilPage / MercadoGlobalPage", () => {
  it("Mercado · Brasil renders without calling any API and shows no live data", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    render(<MercadoBrasilPage />);

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(screen.getByText("Mercado · Brasil")).toBeInTheDocument();
    expect(screen.getByText("Sem dado ao vivo")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("Mercado Global renders without calling any API and shows no live data", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    render(<MercadoGlobalPage />);

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(screen.getByText("Mercado Global")).toBeInTheDocument();
    expect(screen.getByText("Sem dado ao vivo")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("never renders a numeric-looking quote or price", () => {
    render(<MercadoBrasilPage />);
    // Garantia frouxa, mas real: nenhum texto com formato de valor
    // monetário ("R$" seguido de dígito) deve aparecer nesta página.
    expect(screen.queryByText(/R\$\s*\d/)).not.toBeInTheDocument();
  });
});
