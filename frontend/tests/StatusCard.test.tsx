import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusCard } from "@/components/admin/StatusCard";
import type { ComponentStatus } from "@/lib/admin-types";

const baseStatus: ComponentStatus = {
  name: "database",
  online: true,
  detail: "ok",
  latency_ms: 1.4,
  last_heartbeat: new Date().toISOString(),
};

describe("StatusCard", () => {
  it("shows Online with the mapped display name when the component is up", () => {
    render(<StatusCard status={baseStatus} />);
    expect(screen.getByText("Database")).toBeInTheDocument();
    expect(screen.getByText("Online")).toBeInTheDocument();
  });

  it("shows Offline for a down component", () => {
    render(<StatusCard status={{ ...baseStatus, online: false, name: "qdrant" }} />);
    expect(screen.getByText("Offline")).toBeInTheDocument();
  });

  it("falls back to the raw name for a component not in the display map", () => {
    render(<StatusCard status={{ ...baseStatus, name: "some_future_component" }} />);
    expect(screen.getByText("some_future_component")).toBeInTheDocument();
  });
});
