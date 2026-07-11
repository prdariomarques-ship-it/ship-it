"use client";

import { useEffect, useRef, useState } from "react";

export interface SeriesPoint {
  t: number;
  v: number;
}

/** Accumulates polled values into a capped client-side rolling window — the
 * backend exposes cumulative Prometheus counters / point-in-time snapshots,
 * not a time series, so "real-time" charts build their own short history
 * from successive polls (see docs/DASHBOARD.md). Nothing here is persisted;
 * the series resets on page reload, same as any other REST-polled panel. */
export function useRollingSeries(value: number | null | undefined, maxPoints = 30): SeriesPoint[] {
  const [series, setSeries] = useState<SeriesPoint[]>([]);
  const lastValue = useRef<number | null>(null);

  useEffect(() => {
    if (value === null || value === undefined) return;
    if (lastValue.current === value) return;
    lastValue.current = value;
    setSeries((current) => {
      const next = [...current, { t: Date.now(), v: value }];
      return next.length > maxPoints ? next.slice(next.length - maxPoints) : next;
    });
  }, [value, maxPoints]);

  return series;
}

/** Same idea, but converts a cumulative counter into a per-minute rate by
 * diffing consecutive samples — the honest way to show "executions/min"
 * style metrics from a Prometheus Counter without a real time-series
 * backend (see docs/DASHBOARD.md). Returns null until there are two samples
 * to diff. */
export function useRatePerMinute(cumulativeValue: number | null | undefined, maxPoints = 30): SeriesPoint[] {
  const [series, setSeries] = useState<SeriesPoint[]>([]);
  const previous = useRef<{ t: number; v: number } | null>(null);

  useEffect(() => {
    if (cumulativeValue === null || cumulativeValue === undefined) return;
    const now = Date.now();
    if (previous.current) {
      const elapsedMinutes = (now - previous.current.t) / 60_000;
      const delta = cumulativeValue - previous.current.v;
      if (elapsedMinutes > 0 && delta >= 0) {
        const rate = delta / elapsedMinutes;
        setSeries((current) => {
          const next = [...current, { t: now, v: rate }];
          return next.length > maxPoints ? next.slice(next.length - maxPoints) : next;
        });
      }
    }
    previous.current = { t: now, v: cumulativeValue };
  }, [cumulativeValue, maxPoints]);

  return series;
}
