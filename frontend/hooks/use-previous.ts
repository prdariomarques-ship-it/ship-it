"use client";

import { useState } from "react";

/** The value from the previous render — one tick behind `value`. Used by
 * the AI Operator Center to diff CurrentContext snapshots ("what changed
 * since the last poll") without a new backend history endpoint.
 *
 * Tracks "previous" by comparing during render and updating state
 * conditionally — React's documented pattern for derived previous-render
 * state (see "storing information from previous renders" in the useState
 * docs) — rather than reading a ref's value during render, which
 * eslint-plugin-react-hooks now flags as potentially stale under
 * concurrent rendering. */
export function usePrevious<T>(value: T): T | undefined {
  const [state, setState] = useState<{ value: T; previous: T | undefined }>({
    value,
    previous: undefined,
  });
  if (value !== state.value) {
    setState({ value, previous: state.value });
  }
  return state.previous;
}
