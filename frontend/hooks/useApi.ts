"use client";

import { useCallback, useEffect, useState } from "react";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

const ACCESS_KEY = "darioos_token";
const REFRESH_KEY = "darioos_refresh_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}

export function setTokens(access: string | null, refresh?: string | null): void {
  if (typeof window === "undefined") return;
  if (access === null) window.localStorage.removeItem(ACCESS_KEY);
  else window.localStorage.setItem(ACCESS_KEY, access);
  if (refresh !== undefined) {
    if (refresh === null) window.localStorage.removeItem(REFRESH_KEY);
    else window.localStorage.setItem(REFRESH_KEY, refresh);
  }
}

// Tokens rotate on refresh, so concurrent 401s must share one refresh call —
// a second rotation with the same token would be rejected and log the user out.
let refreshInFlight: Promise<boolean> | null = null;

async function doRefresh(): Promise<boolean> {
  const refresh = window.localStorage.getItem(REFRESH_KEY);
  if (!refresh) return false;
  const response = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!response.ok) {
    setTokens(null, null);
    return false;
  }
  const pair = await response.json();
  setTokens(pair.access_token, pair.refresh_token);
  return true;
}

async function tryRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/** Error carrying the HTTP status and the raw `detail` (string, or the bridge's `{message, code, ...}` object). */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// `detail` is a string for most endpoints, an object `{message, code, ...}` for the DARIUS bridge and an
// array for FastAPI validation errors. Strings keep the previous behaviour; objects no longer degrade to
// "[object Object]".
function apiError(status: number, detail: unknown): ApiError {
  let message = `Request failed: ${status}`;
  if (typeof detail === "string" && detail) message = detail;
  else if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const text = (detail as { message?: unknown }).message;
    if (typeof text === "string" && text) message = text;
  }
  return new ApiError(message, status, detail);
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  retried = false
): Promise<T> {
  const token = getToken();
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (response.status === 401 && typeof window !== "undefined" && token) {
    // Access token expired: rotate the refresh token once, then retry.
    // Only applies to requests that carried a token — an anonymous 401
    // (e.g. a failed /auth/login attempt) is a normal error the caller
    // should handle, not a session expiry to redirect away from.
    if (!retried && (await tryRefresh())) {
      return apiFetch<T>(path, options, true);
    }
    window.location.href = "/login";
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw apiError(response.status, body.detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useApi<T>(path: string): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    let active = true;

    async function run() {
      setLoading(true);
      try {
        const result = await apiFetch<T>(path);
        if (active) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (active) setError((err as Error).message);
      } finally {
        if (active) setLoading(false);
      }
    }

    run();
    return () => {
      active = false;
    };
  }, [path, version]);

  return { data, loading, error, reload };
}
