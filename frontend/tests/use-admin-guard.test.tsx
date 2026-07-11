import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const replaceMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
}));

vi.mock("@/hooks/useApi", () => ({
  apiFetch: vi.fn(),
  getToken: vi.fn(),
}));

import { apiFetch, getToken } from "@/hooks/useApi";
import { useAdminGuard } from "@/hooks/use-admin-guard";

const mockedApiFetch = vi.mocked(apiFetch);
const mockedGetToken = vi.mocked(getToken);

describe("useAdminGuard", () => {
  it("redirects to /login when there is no token at all", () => {
    mockedGetToken.mockReturnValue(null);
    const { result } = renderHook(() => useAdminGuard());
    expect(result.current.status).toBe("loading");
    expect(replaceMock).toHaveBeenCalledWith("/login");
  });

  it("resolves to 'ok' with the user when /auth/me reports role=admin", async () => {
    mockedGetToken.mockReturnValue("a-real-token");
    mockedApiFetch.mockResolvedValue({
      id: 1, email: "admin@dario.os", full_name: "Admin", role: "admin", is_active: true,
    });
    const { result } = renderHook(() => useAdminGuard());
    await waitFor(() => expect(result.current.status).toBe("ok"));
    if (result.current.status === "ok") {
      expect(result.current.user.email).toBe("admin@dario.os");
    }
  });

  it("resolves to 'denied' when /auth/me reports a non-admin role", async () => {
    mockedGetToken.mockReturnValue("a-real-token");
    mockedApiFetch.mockResolvedValue({
      id: 2, email: "user@dario.os", full_name: "User", role: "user", is_active: true,
    });
    const { result } = renderHook(() => useAdminGuard());
    await waitFor(() => expect(result.current.status).toBe("denied"));
  });

  it("resolves to 'denied' when /auth/me itself fails (e.g. expired token)", async () => {
    mockedGetToken.mockReturnValue("a-stale-token");
    mockedApiFetch.mockRejectedValue(new Error("401"));
    const { result } = renderHook(() => useAdminGuard());
    await waitFor(() => expect(result.current.status).toBe("denied"));
  });
});
