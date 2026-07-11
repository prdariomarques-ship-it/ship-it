import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AdminPageHeader } from "@/components/admin/PageHeader";

describe("AdminPageHeader", () => {
  it("renders the title and optional subtitle", () => {
    render(<AdminPageHeader title="Agents" subtitle="Lista de agentes" />);
    expect(screen.getByText("Agents")).toBeInTheDocument();
    expect(screen.getByText("Lista de agentes")).toBeInTheDocument();
  });

  it("renders optional actions", () => {
    render(<AdminPageHeader title="Settings" actions={<button>read-only</button>} />);
    expect(screen.getByRole("button", { name: "read-only" })).toBeInTheDocument();
  });

  it("omits the subtitle paragraph when none is given", () => {
    const { container } = render(<AdminPageHeader title="Only title" />);
    expect(container.querySelectorAll("p").length).toBe(0);
  });
});
