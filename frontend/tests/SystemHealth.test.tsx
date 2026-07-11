import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SystemHealth } from "@/components/admin/SystemHealth";

describe("SystemHealth", () => {
  it("renders CPU, memory and disk gauges without crashing", () => {
    render(
      <SystemHealth
        cpuPercent={12.5}
        memoryPercent={40}
        memoryUsedMb={2000}
        memoryTotalMb={5000}
        diskPercent={20}
        diskUsedGb={10}
        diskTotalGb={50}
      />
    );
    expect(screen.getByText("CPU")).toBeInTheDocument();
    expect(screen.getByText("Memória")).toBeInTheDocument();
    expect(screen.getByText("Disco")).toBeInTheDocument();
    expect(screen.getByText("2000 MB / 5000 MB")).toBeInTheDocument();
  });

  it("handles null resource values (psutil unavailable) gracefully", () => {
    render(
      <SystemHealth
        cpuPercent={null}
        memoryPercent={null}
        memoryUsedMb={null}
        memoryTotalMb={null}
        diskPercent={null}
        diskUsedGb={null}
        diskTotalGb={null}
      />
    );
    expect(screen.getAllByText("—").length).toBe(3);
  });
});
