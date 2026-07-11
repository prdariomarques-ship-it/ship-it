"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { apiFetch, getToken } from "@/hooks/useApi";

interface Me {
  id: number;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
}

type GuardState =
  | { status: "loading" }
  | { status: "denied" }
  | { status: "ok"; user: Me };

/** Client-side ADMIN gate for the whole /admin section. The backend already
 * enforces this on every /api/admin/* call (403 for non-admins) — this hook
 * only avoids flashing admin UI at a user who will get 403s on every
 * request, by checking the same `role` field via the existing `/auth/me`. */
export function useAdminGuard(): GuardState {
  const router = useRouter();
  const [state, setState] = useState<GuardState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    apiFetch<Me>("/auth/me")
      .then((me) => {
        if (!active) return;
        if (me.role !== "admin") {
          setState({ status: "denied" });
          return;
        }
        setState({ status: "ok", user: me });
      })
      .catch(() => {
        if (active) setState({ status: "denied" });
      });
    return () => {
      active = false;
    };
  }, [router]);

  return state;
}
