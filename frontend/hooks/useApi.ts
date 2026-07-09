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

async function tryRefresh(): Promise<boolean> {
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

  if (response.status === 401 && typeof window !== "undefined") {
    // Access token expired: rotate the refresh token once, then retry.
    if (!retried && (await tryRefresh())) {
      return apiFetch<T>(path, options, true);
    }
    window.location.href = "/login";
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed: ${response.status}`);
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
    setLoading(true);
    apiFetch<T>(path)
      .then((result) => {
        if (active) {
          setData(result);
          setError(null);
        }
      })
      .catch((err: Error) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [path, version]);

  return { data, loading, error, reload };
}
