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

  it("labels a queued observation.tick as 'rodando', not 'queued'", () => {
    // observation.tick is created at the start of its ~5min cycle and only
    // flips to succeeded when the *next* cycle starts, so "queued" reads as
    // stuck even though it's just mid-cycle (HOMOLOGATION_REPORT_v1.3.1.md).
    // Scoped to this one job name — a real queued-and-waiting job elsewhere
    // in the list must still say "queued".
    const entries: ExecutionEntry[] = [
      {
        kind: "job",
        id: 3,
        timestamp: new Date().toISOString(),
        name: "observation.tick",
        agent: null,
        status: "queued",
        detail: "",
        duration_seconds: null,
      },
      {
        kind: "job",
        id: 4,
        timestamp: new Date().toISOString(),
        name: "whatsapp.send_text",
        agent: null,
        status: "queued",
        detail: "",
        duration_seconds: null,
      },
    ];
    render(<ExecutionTimeline entries={entries} />);
    expect(screen.getByText("rodando")).toBeInTheDocument();
    expect(screen.getByText("queued")).toBeInTheDocument();
  });
});
