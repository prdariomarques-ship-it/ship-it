import { render, screen } from "@testing-library/react";
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
});
