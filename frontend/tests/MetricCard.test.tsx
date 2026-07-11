import { render, screen } from "@testing-library/react";
import { Bot } from "lucide-react";
import { describe, expect, it } from "vitest";

import { MetricCard } from "@/components/admin/MetricCard";

describe("MetricCard", () => {
  it("renders the label and value", () => {
    render(<MetricCard label="Usuários" value={42} />);
    expect(screen.getByText("Usuários")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders an optional hint", () => {
    render(<MetricCard label="Uptime" value="2min" hint="desde o último deploy" />);
    expect(screen.getByText("desde o último deploy")).toBeInTheDocument();
  });

  it("renders an optional icon without crashing", () => {
    render(<MetricCard label="Agents" value={5} icon={Bot} />);
    expect(screen.getByText("Agents")).toBeInTheDocument();
  });
});
