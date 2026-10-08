import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/mercado-brasil",
}));

import Sidebar from "@/components/Sidebar";

// jsdom não implementa matchMedia — mock controlável por teste, pra
// exercitar o comportamento real de mobile vs. desktop (inert quando a
// gaveta está fechada no mobile), não só simular o clique do botão.
function mockMatchMedia(matches: boolean) {
  const listeners = new Set<() => void>();
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    addEventListener: (_: string, cb: () => void) => listeners.add(cb),
    removeEventListener: (_: string, cb: () => void) => listeners.delete(cb),
  })) as unknown as typeof window.matchMedia;
}

describe("Sidebar", () => {
  beforeEach(() => {
    mockMatchMedia(false); // desktop por padrão — testes de mobile chamam de novo com true
  });


  it("renders the main navigation landmark", () => {
    render(<Sidebar />);
    expect(screen.getByRole("navigation", { name: "Navegação principal" })).toBeInTheDocument();
  });

  it("marks the current route's link active and others not", () => {
    render(<Sidebar />);
    const current = screen.getByRole("link", { name: "Mercado · Brasil" });
    expect(current).toHaveClass("active");
    expect(current).toHaveAttribute("aria-current", "page");

    const other = screen.getByRole("link", { name: "Loja" });
    expect(other).not.toHaveClass("active");
    expect(other).not.toHaveAttribute("aria-current");
  });

  // Proteção explícita: Gêmeo Darius e Conversas pessoais nunca viram
  // link clicável nem apontam para /messages genérico — ver
  // DARIUS_OS_FRONTEND_STATUS.md / INTEGRATION_STATUS.md.
  it("renders Gêmeo Darius and Conversas pessoais as disabled, not as links", () => {
    render(<Sidebar />);

    expect(screen.queryByRole("link", { name: "Gêmeo Darius" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Conversas pessoais/ })).not.toBeInTheDocument();

    const twin = screen.getByText("Gêmeo Darius").closest('[aria-disabled="true"]');
    expect(twin).toHaveAttribute("aria-disabled", "true");
    expect(twin).toHaveTextContent("Rota dedicada não encontrada");

    const personalConversations = screen
      .getByText("Conversas pessoais")
      .closest('[aria-disabled="true"]');
    expect(personalConversations).toHaveAttribute("aria-disabled", "true");
    expect(personalConversations).toHaveTextContent("Filtro pessoal não comprovado");
  });

  it("does not route Conversas pessoais to the generic /conversas link", () => {
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: "Conversas" })).toHaveAttribute("href", "/conversas");
    expect(screen.queryByRole("link", { name: /Conversas pessoais/ })).toBeNull();
  });

  // Funcionalidades do master que precisam continuar presentes — ver
  // apontamento explícito sobre remoções indevidas.
  it("preserves Contatos, Metas, Notas and Briefings from the approved base", () => {
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: "Contatos" })).toHaveAttribute("href", "/contatos");
    expect(screen.getByRole("link", { name: "Metas" })).toHaveAttribute("href", "/metas");
    expect(screen.getByRole("link", { name: "Notas" })).toHaveAttribute("href", "/notas");
    expect(screen.getByRole("link", { name: "Briefings" })).toHaveAttribute("href", "/admin/briefing");
  });

  it("links Logs to the real existing route /admin/logs, not a nonexistent /logs", () => {
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: "Logs" })).toHaveAttribute("href", "/admin/logs");
  });

  it("mobile menu toggle opens the drawer and moves focus to the first link", async () => {
    mockMatchMedia(true); // viewport mobile — é onde o foco no primeiro link importa
    const user = userEvent.setup();
    render(<Sidebar />);

    const toggle = screen.getByRole("button", { name: "Abrir navegação" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-controls", "darius-sidebar-nav");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveAccessibleName("Fechar navegação");

    // O título do teste promete foco no primeiro link — isto precisa
    // ser verificado de fato, não só o estado do botão.
    const firstLink = screen.getByRole("link", { name: "Visão geral" });
    expect(firstLink).toHaveFocus();
  });

  it("Escape closes the drawer and returns focus to the toggle button", async () => {
    mockMatchMedia(true);
    const user = userEvent.setup();
    render(<Sidebar />);

    const toggle = screen.getByRole("button", { name: "Abrir navegação" });
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    await user.keyboard("{Escape}");

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAccessibleName("Abrir navegação");
    expect(toggle).toHaveFocus();
  });

  // Achado da revisão de código: a gaveta fechada no mobile só ficava
  // fora da tela visualmente (transform), continuando focável/tabulável
  // — links invisíveis entrando na ordem de Tab. Corrigido com `inert`.
  describe("teclado — gaveta fora da ordem de Tab quando fechada no mobile", () => {
    it("is inert when closed on a mobile viewport", () => {
      mockMatchMedia(true);
      render(<Sidebar />);
      const nav = screen.getByRole("navigation", { name: "Navegação principal" });
      expect(nav).toHaveAttribute("inert");
    });

    it("is not inert once opened on a mobile viewport", async () => {
      mockMatchMedia(true);
      const user = userEvent.setup();
      render(<Sidebar />);

      const nav = screen.getByRole("navigation", { name: "Navegação principal" });
      expect(nav).toHaveAttribute("inert");

      await user.click(screen.getByRole("button", { name: "Abrir navegação" }));

      expect(nav).not.toHaveAttribute("inert");
    });

    it("is never inert on a desktop viewport, open or closed", () => {
      mockMatchMedia(false);
      render(<Sidebar />);
      const nav = screen.getByRole("navigation", { name: "Navegação principal" });
      expect(nav).not.toHaveAttribute("inert");
    });
  });
});
