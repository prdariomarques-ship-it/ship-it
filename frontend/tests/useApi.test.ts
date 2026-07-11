import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch, setTokens } from "@/hooks/useApi";

describe("apiFetch 401 handling", () => {
  const originalLocation = window.location;

  beforeEach(() => {
    window.localStorage.clear();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { href: "" },
    });
  });

  afterEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
    vi.restoreAllMocks();
  });

  it("throws a normal Error (no redirect) on a 401 from an unauthenticated request", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: "Invalid credentials" }),
      })
    );

    await expect(apiFetch("/auth/login", { method: "POST" })).rejects.toThrow("Invalid credentials");
    expect(window.location.href).toBe("");
  });

  it("redirects to /login on a 401 for a request that carried an access token with no refresh token available", async () => {
    setTokens("expired-access-token", null);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: "Token expired" }),
      })
    );

    await apiFetch("/dashboard/summary").catch(() => {});
    expect(window.location.href).toBe("/login");
  });
});
