import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ExecutionTimeline } from "@/components/admin/ExecutionTimeline";
import type { ExecutionEntry } from "@/lib/admin-types";

describe("ExecutionTimeline", () => {
  it("shows an empty state when there are no entries", () => {
    render(<ExecutionTimeline entries={[]} />);
    expect(screen.getByText("Nenhuma execução no período")).toBeInTheDocument();
  });

  it("renders job and log entries with their status badges", () => {
    const entries: ExecutionEntry[] = [
      {
        kind: "job",
        id: 1,
        timestamp: new Date().toISOString(),
        name: "whatsapp.process_inbound",
        agent: null,
        status: "succeeded",
        detail: "",
        duration_seconds: 1.2,
      },
      {
        kind: "log",
        id: 2,
        timestamp: new Date().toISOString(),
        name: "agent:personal",
        agent: "personal",
        status: "info",
        detail: "Respondeu",
        duration_seconds: null,
      },
    ];
    render(<ExecutionTimeline entries={entries} />);
    expect(screen.getByText("whatsapp.process_inbound")).toBeInTheDocument();
    expect(screen.getByText("succeeded")).toBeInTheDocument();
    expect(screen.getByText("agent:personal")).toBeInTheDocument();
    expect(screen.getByText("personal")).toBeInTheDocument();
  });
});
