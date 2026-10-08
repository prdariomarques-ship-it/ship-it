import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Qualquer chamada de rede aqui faria este teste falhar por engano de
// fetch não mockado — a proteção que queremos comprovar é que a página
// NUNCA tenta. Não precisa de mock de fetch porque, se a página chamar
// fetch, o jsdom lançaria "fetch is not defined" e o teste falharia.
import PessoalPage from "@/app/(dashboard)/pessoal/page";

describe("PessoalPage", () => {
  it("renders without calling any API", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    render(<PessoalPage />);

    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("states Gêmeo Darius is unavailable, with the real reason", () => {
    render(<PessoalPage />);
    expect(screen.getByText("Gêmeo Darius")).toBeInTheDocument();
    expect(screen.getByText("Rota dedicada não encontrada")).toBeInTheDocument();
  });

  it("states Conversas pessoais is unavailable and explains the unproven filter, not a fake conversation list", () => {
    render(<PessoalPage />);
    expect(screen.getByText("Conversas pessoais")).toBeInTheDocument();
    expect(screen.getByText("Filtro pessoal não comprovado")).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});
