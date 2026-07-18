import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/agents",
}));

import { AdminSidebar } from "@/components/admin/AdminSidebar";

describe("AdminSidebar", () => {
  it("renders all 15 menu items (12 from the original spec + Timeline/Phase 2 + Briefing Diário/Phase 3 + Central de Ações/Phase 4)", () => {
    render(<AdminSidebar />);
    const labels = [
      "Dashboard", "Briefing Diário", "Central de Ações", "Timeline", "Agents", "Tools", "Executions", "Memory (vector)",
      "Google Workspace", "WhatsApp", "Users", "Logs", "Metrics", "System", "Settings",
    ];
    for (const label of labels) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("marks the current route's link as active", () => {
    render(<AdminSidebar />);
    const link = screen.getByText("Agents").closest("a");
    expect(link).toHaveClass("text-primary");
  });

  it("does not mark the Dashboard link active on a nested route (exact match only)", () => {
    render(<AdminSidebar />);
    const link = screen.getByText("Dashboard").closest("a");
    expect(link).not.toHaveClass("text-primary");
  });

  // Mobile drawer — see RC1_AUDIT.md Finding #1 (no mobile-responsive sidebar).
  it("is translated off-screen when closed (mobile default) and on-screen when open", () => {
    const { rerender } = render(<AdminSidebar open={false} />);
    expect(screen.getByRole("navigation")).toHaveClass("-translate-x-full");

    rerender(<AdminSidebar open />);
    expect(screen.getByRole("navigation")).toHaveClass("translate-x-0");
  });

  it("stays visible on desktop regardless of the mobile open state", () => {
    render(<AdminSidebar open={false} />);
    expect(screen.getByRole("navigation")).toHaveClass("md:translate-x-0");
  });

  it("calls onClose when the close button is clicked", () => {
    const onClose = vi.fn();
    render(<AdminSidebar open onClose={onClose} />);
    fireEvent.click(screen.getByLabelText("Fechar menu"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when a nav link is clicked (closes the drawer on navigation)", () => {
    const onClose = vi.fn();
    render(<AdminSidebar open onClose={onClose} />);
    fireEvent.click(screen.getByText("Timeline"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when Escape is pressed while open", () => {
    const onClose = vi.fn();
    render(<AdminSidebar open onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("does not listen for Escape when closed", () => {
    const onClose = vi.fn();
    render(<AdminSidebar open={false} onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("renders a backdrop only when open", () => {
    const { container, rerender } = render(<AdminSidebar open={false} />);
    expect(container.querySelector('div[aria-hidden="true"]')).toBeNull();

    rerender(<AdminSidebar open />);
    expect(container.querySelector('div[aria-hidden="true"]')).not.toBeNull();
  });
});
