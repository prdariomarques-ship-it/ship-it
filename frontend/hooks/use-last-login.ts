"use client";

import { useEffect, useState } from "react";

// No backend session-history table exists (and adding one just for this
// would be new infrastructure) — "last login" here means "the last time
// this browser opened the admin dashboard", tracked client-side. Good
// enough for a single-owner system (Dario OS isn't multi-tenant), and
// exactly what "what changed since my last login?" needs: a timestamp to
// diff against, not an audit-grade session log.

const STORAGE_KEY = "darioos_last_login_at";

function readPreviousLogin(): Date | null {
  if (typeof window === "undefined") return null;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored ? new Date(stored) : null;
}

export function useLastLogin(): Date | null {
  // Read once, as the lazy initial state (runs during the initial render,
  // not as a setState call inside an effect) -- this hook is only ever
  // consumed behind useAdminGuard's client-side loading gate (see
  // AdminShell), so there's no server-rendered content depending on this
  // value to hydration-match against.
  const [previousLogin] = useState<Date | null>(readPreviousLogin);

  useEffect(() => {
    // The write is the actual side effect (recording *this* visit for next
    // time) -- distinct from the read above, which only initializes state.
    window.localStorage.setItem(STORAGE_KEY, new Date().toISOString());
  }, []);

  return previousLogin;
}
