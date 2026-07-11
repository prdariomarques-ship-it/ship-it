import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useRatePerMinute, useRollingSeries } from "@/hooks/use-rolling-series";

describe("useRollingSeries", () => {
  it("starts empty and accumulates one point per distinct value", () => {
    const { result, rerender } = renderHook(({ value }: { value: number | null }) => useRollingSeries(value), {
      initialProps: { value: null as number | null },
    });
    expect(result.current).toEqual([]);

    rerender({ value: 10 });
    expect(result.current).toHaveLength(1);
    expect(result.current[0].v).toBe(10);

    rerender({ value: 20 });
    expect(result.current).toHaveLength(2);
  });

  it("ignores a repeated identical value (no duplicate point)", () => {
    const { result, rerender } = renderHook(({ value }: { value: number | null }) => useRollingSeries(value), {
      initialProps: { value: 5 as number | null },
    });
    rerender({ value: 5 });
    rerender({ value: 5 });
    expect(result.current).toHaveLength(1);
  });

  it("caps the series at maxPoints", () => {
    const { result, rerender } = renderHook(
      ({ value }: { value: number | null }) => useRollingSeries(value, 3),
      { initialProps: { value: 1 as number | null } }
    );
    rerender({ value: 2 });
    rerender({ value: 3 });
    rerender({ value: 4 });
    expect(result.current).toHaveLength(3);
    expect(result.current.map((p) => p.v)).toEqual([2, 3, 4]);
  });
});

describe("useRatePerMinute", () => {
  it("produces no point from a single sample (needs a diff)", () => {
    const { result } = renderHook(({ value }: { value: number | null }) => useRatePerMinute(value), {
      initialProps: { value: 10 as number | null },
    });
    expect(result.current).toEqual([]);
  });

  it("never produces a negative rate from a counter reset", () => {
    // A Prometheus Counter can only go up within a process; if it drops
    // (process restart), the honest thing is to skip that sample, not
    // report a nonsensical negative "rate".
    let now = 1_700_000_000_000;
    const originalNow = Date.now;
    Date.now = () => now;

    const { result, rerender } = renderHook(
      ({ value }: { value: number | null }) => useRatePerMinute(value),
      { initialProps: { value: 100 as number | null } }
    );
    now += 60_000;
    rerender({ value: 20 }); // counter went down (reset)

    Date.now = originalNow;
    expect(result.current).toEqual([]);
  });

  it("computes a per-minute rate by diffing two samples one minute apart", () => {
    let now = 1_700_000_000_000;
    const originalNow = Date.now;
    Date.now = () => now;

    const { result, rerender } = renderHook(
      ({ value }: { value: number | null }) => useRatePerMinute(value),
      { initialProps: { value: 10 as number | null } }
    );
    now += 60_000; // exactly one minute later
    rerender({ value: 40 }); // +30 over one minute = 30/min

    Date.now = originalNow;
    expect(result.current).toHaveLength(1);
    expect(result.current[0].v).toBe(30);
  });
});
