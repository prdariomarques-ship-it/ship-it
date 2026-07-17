import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useOperatorInsightState } from "@/hooks/use-operator-state";

describe("useOperatorInsightState", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("nothing is hidden before any action", () => {
    const { result } = renderHook(() => useOperatorInsightState());
    expect(result.current.isHidden("missed-1")).toBe(false);
  });

  it("dismiss hides an insight", () => {
    const { result } = renderHook(() => useOperatorInsightState());
    act(() => result.current.dismiss("missed-1"));
    expect(result.current.isHidden("missed-1")).toBe(true);
  });

  it("complete hides an insight", () => {
    const { result } = renderHook(() => useOperatorInsightState());
    act(() => result.current.complete("approve-2"));
    expect(result.current.isHidden("approve-2")).toBe(true);
  });

  it("snooze hides an insight until the snooze window elapses", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-17T12:00:00Z"));
    const { result } = renderHook(() => useOperatorInsightState());

    act(() => result.current.snooze("retry-3"));
    expect(result.current.isHidden("retry-3")).toBe(true);

    vi.setSystemTime(new Date("2026-07-17T16:00:01Z")); // just past the 4h default
    expect(result.current.isHidden("retry-3")).toBe(false);
  });

  it("restore un-hides a dismissed insight", () => {
    const { result } = renderHook(() => useOperatorInsightState());
    act(() => result.current.dismiss("missed-1"));
    expect(result.current.isHidden("missed-1")).toBe(true);
    act(() => result.current.restore("missed-1"));
    expect(result.current.isHidden("missed-1")).toBe(false);
  });

  it("persists across remounts (a fresh render reads the same localStorage)", () => {
    const first = renderHook(() => useOperatorInsightState());
    act(() => first.result.current.dismiss("missed-1"));

    const second = renderHook(() => useOperatorInsightState());
    expect(second.result.current.isHidden("missed-1")).toBe(true);
  });

  it("dismissing one insight does not affect another", () => {
    const { result } = renderHook(() => useOperatorInsightState());
    act(() => result.current.dismiss("missed-1"));
    expect(result.current.isHidden("missed-2")).toBe(false);
  });
});
