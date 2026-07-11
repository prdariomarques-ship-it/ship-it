import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AgentCard } from "@/components/admin/AgentCard";
import type { AgentAdminInfo } from "@/lib/admin-types";

const baseAgent: AgentAdminInfo = {
  name: "personal",
  description: "Assistente pessoal",
  tool_count: 8,
  runs_total: 12,
  runs_ok: 10,
  runs_error: 2,
  avg_duration_seconds: 2.5,
  last_execution: new Date().toISOString(),
};

describe("AgentCard", () => {
  it("shows a destructive badge with the error count when there are errors", () => {
    render(<AgentCard agent={baseAgent} />);
    expect(screen.getByText("2 erro(s)")).toBeInTheDocument();
  });

  it("shows a healthy badge when there are no errors", () => {
    render(<AgentCard agent={{ ...baseAgent, runs_error: 0 }} />);
    expect(screen.getByText("saudável")).toBeInTheDocument();
  });

  it("honestly shows 'não disponível' instead of 0 when stats were never collected", () => {
    render(
      <AgentCard
        agent={{ ...baseAgent, runs_total: null, runs_ok: null, runs_error: null, avg_duration_seconds: null }}
      />
    );
    expect(screen.getAllByText("não disponível").length).toBeGreaterThan(0);
  });

  it("shows 'sem registro' when there is no last execution timestamp", () => {
    render(<AgentCard agent={{ ...baseAgent, last_execution: null }} />);
    expect(screen.getByText("sem registro")).toBeInTheDocument();
  });
});
