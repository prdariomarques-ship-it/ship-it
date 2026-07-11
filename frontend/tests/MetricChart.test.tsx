import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MetricChart } from "@/components/admin/charts/MetricChart";

describe("MetricChart", () => {
  it("shows a 'collecting data' empty state with fewer than two points", () => {
    render(<MetricChart data={[]} />);
    expect(screen.getByText("Coletando dados…")).toBeInTheDocument();

    render(<MetricChart data={[{ t: Date.now(), v: 1 }]} />);
    expect(screen.getAllByText("Coletando dados…").length).toBeGreaterThan(0);
  });

  it("renders a chart container once there are at least two points", () => {
    const { container } = render(
      <MetricChart data={[{ t: Date.now() - 1000, v: 1 }, { t: Date.now(), v: 2 }]} />
    );
    expect(container.querySelector(".recharts-responsive-container")).toBeInTheDocument();
  });
});
