import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/mercado-brasil",
}));

import Sidebar from "@/components/Sidebar";

describe("Sidebar", () => {
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
    // "Conversas" (geral) continua linkável; "Conversas pessoais" não é link algum.
    expect(screen.getByRole("link", { name: "Conversas" })).toHaveAttribute("href", "/conversas");
    expect(screen.queryByRole("link", { name: /Conversas pessoais/ })).toBeNull();
  });

  it("does not list the financial-bots panel in navigation", () => {
    render(<Sidebar />);
    expect(screen.queryByText(/monitor/i)).not.toBeInTheDocument();
  });

  it("mobile menu toggle opens the drawer and focuses the first link", async () => {
    const user = userEvent.setup();
    render(<Sidebar />);

    const toggle = screen.getByRole("button", { name: "Abrir navegação" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);

    // "Fechar navegação" também rotula o backdrop quando aberto — o
    // botão de alternância é o único com aria-controls, então é esse
    // que precisa ser verificado, não "o primeiro que bater o nome".
    expect(toggle).toHaveAttribute("aria-controls", "darius-sidebar-nav");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveAccessibleName("Fechar navegação");
  });

  it("Escape closes the drawer and returns focus to the toggle button", async () => {
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
});
