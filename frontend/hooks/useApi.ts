"use client";

import { useCallback, useEffect, useState } from "react";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("darioos_token");
}

export function setToken(token: string | null): void {
  if (token === null) window.localStorage.removeItem("darioos_token");
  else window.localStorage.setItem("darioos_token", token);
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (response.status === 401 && typeof window !== "undefined") {
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
