"use client";

import { useCallback, useEffect, useState } from "react";

// Dismiss/snooze/complete are per-browser preferences about an ephemeral,
// recomputed-every-poll recommendation — not a durable business record, so
// this is deliberately localStorage, not a new backend endpoint (see
// AI_OPERATOR.md). Insight ids are stable per underlying record (e.g.
// `missed-3` for task id 3), so a dismissal survives the next poll for the
// same task, but naturally disappears once the underlying condition does
// (the task is no longer overdue) since that id simply stops being generated.

const STORAGE_KEY = "darioos_operator_insight_state";
const SNOOZE_HOURS = 4;

type InsightStatus = "dismissed" | "completed" | "snoozed";

interface StoredEntry {
  status: InsightStatus;
  until?: number;
}

type StoredState = Record<string, StoredEntry>;

function readStorage(): StoredState {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredState) : {};
  } catch {
    return {};
  }
}

function writeStorage(state: StoredState): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export interface OperatorInsightState {
  isHidden: (id: string) => boolean;
  dismiss: (id: string) => void;
  complete: (id: string) => void;
  snooze: (id: string, hours?: number) => void;
  restore: (id: string) => void;
}

export function useOperatorInsightState(): OperatorInsightState {
  const [state, setState] = useState<StoredState>({});

  useEffect(() => {
    setState(readStorage());
  }, []);

  const update = useCallback((id: string, entry: StoredEntry | null) => {
    setState((current) => {
      const next = { ...current };
      if (entry === null) delete next[id];
      else next[id] = entry;
      writeStorage(next);
      return next;
    });
  }, []);

  const isHidden = useCallback(
    (id: string) => {
      const entry = state[id];
      if (!entry) return false;
      if (entry.status === "snoozed" && entry.until) {
        return Date.now() < entry.until;
      }
      return entry.status === "dismissed" || entry.status === "completed";
    },
    [state]
  );

  const dismiss = useCallback((id: string) => update(id, { status: "dismissed" }), [update]);
  const complete = useCallback((id: string) => update(id, { status: "completed" }), [update]);
  const snooze = useCallback(
    (id: string, hours: number = SNOOZE_HOURS) =>
      update(id, { status: "snoozed", until: Date.now() + hours * 3_600_000 }),
    [update]
  );
  const restore = useCallback((id: string) => update(id, null), [update]);

  return { isHidden, dismiss, complete, snooze, restore };
}
