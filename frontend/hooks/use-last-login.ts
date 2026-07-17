"use client";

import { useEffect, useState } from "react";

// No backend session-history table exists (and adding one just for this
// would be new infrastructure) — "last login" here means "the last time
// this browser opened the admin dashboard", tracked client-side. Good
// enough for a single-owner system (Dario OS isn't multi-tenant), and
// exactly what "what changed since my last login?" needs: a timestamp to
// diff against, not an audit-grade session log.

const STORAGE_KEY = "darioos_last_login_at";

export function useLastLogin(): Date | null {
  const [previousLogin, setPreviousLogin] = useState<Date | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) setPreviousLogin(new Date(stored));
    window.localStorage.setItem(STORAGE_KEY, new Date().toISOString());
  }, []);

  return previousLogin;
}
