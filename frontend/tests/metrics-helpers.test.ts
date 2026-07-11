import { describe, expect, it } from "vitest";

import { sumMetric } from "@/lib/metrics-helpers";
import type { MetricsSnapshot } from "@/lib/admin-types";

describe("sumMetric", () => {
  it("returns 0 when the snapshot is undefined", () => {
    expect(sumMetric(undefined, "darioos_agent_runs_total")).toBe(0);
  });

  it("sums only samples with the exact sample name, across every metric-family group", () => {
    // Mirrors the real shape backend/admin/service.py::prometheus_snapshot()
    // produces: samples grouped by Prometheus's *base* metric name, not by
    // their own (possibly suffixed) sample name — this is the exact bug
    // this helper's backend counterpart (_metric_value) had until fixed.
    const snapshot: MetricsSnapshot = {
      timestamp: "2026-01-01T00:00:00Z",
      metrics: {
        darioos_agent_runs: [
          { name: "darioos_agent_runs_total", labels: { agent: "personal", status: "ok" }, value: 3 },
          { name: "darioos_agent_runs_total", labels: { agent: "personal", status: "error" }, value: 1 },
          { name: "darioos_agent_runs_created", labels: { agent: "personal", status: "ok" }, value: 1783731684 },
        ],
      },
    };

    expect(sumMetric(snapshot, "darioos_agent_runs_total", { agent: "personal", status: "ok" })).toBe(3);
    expect(sumMetric(snapshot, "darioos_agent_runs_total")).toBe(4);
    expect(sumMetric(snapshot, "darioos_agent_runs_created")).toBe(1783731684);
  });

  it("sums across multiple label combinations when the filter under-specifies", () => {
    const snapshot: MetricsSnapshot = {
      timestamp: "2026-01-01T00:00:00Z",
      metrics: {
        darioos_agent_tokens: [
          { name: "darioos_agent_tokens_total", labels: { provider: "openai", kind: "prompt" }, value: 100 },
          { name: "darioos_agent_tokens_total", labels: { provider: "openai", kind: "completion" }, value: 50 },
          { name: "darioos_agent_tokens_total", labels: { provider: "anthropic", kind: "prompt" }, value: 10 },
        ],
      },
    };

    expect(sumMetric(snapshot, "darioos_agent_tokens_total", { kind: "prompt" })).toBe(110);
  });

  it("returns 0 when no sample matches the given name", () => {
    const snapshot: MetricsSnapshot = { timestamp: "2026-01-01T00:00:00Z", metrics: {} };
    expect(sumMetric(snapshot, "does_not_exist")).toBe(0);
  });
});
