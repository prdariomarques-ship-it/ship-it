"use client";

import { useEffect, useRef } from "react";

/** The value from the previous render — one tick behind `value`. Used by
 * the AI Operator Center to diff CurrentContext snapshots ("what changed
 * since the last poll") without a new backend history endpoint. */
export function usePrevious<T>(value: T): T | undefined {
  const ref = useRef<T>();
  useEffect(() => {
    ref.current = value;
  }, [value]);
  return ref.current;
}
