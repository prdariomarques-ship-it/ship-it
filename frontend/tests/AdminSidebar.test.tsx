import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/agents",
}));

import { AdminSidebar } from "@/components/admin/AdminSidebar";

describe("AdminSidebar", () => {
  it("renders without crashing and contains sidebar navigation", () => {
    render(<AdminSidebar />);
    const nav = screen.getByRole("navigation");
    expect(nav).toBeInTheDocument();
  });

  it("marks the current route's link as active", () => {
    render(<AdminSidebar />);
    // Find the Agents link (not confused with other items)
    const allLinks = screen.getAllByText("Agents");
    const agentsLink = allLinks.find(el => el.closest("a"));
    expect(agentsLink?.closest("a")).toHaveClass("text-primary");
  });

  it("does not mark the Dashboard link active on a nested route (exact match only)", () => {
    render(<AdminSidebar />);
    const links = screen.getAllByText("Dashboard");
    const dashboardLink = links.find(el => el.closest("a"));
    expect(dashboardLink?.closest("a")).not.toHaveClass("text-primary");
  });
});
