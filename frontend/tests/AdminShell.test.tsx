import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/use-admin-guard", () => ({
  useAdminGuard: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/admin",
  useRouter: () => ({ replace: vi.fn() }),
}));
vi.mock("@/hooks/useApi", () => ({
  apiFetch: vi.fn(() => new Promise(() => {})),
}));

import { useAdminGuard } from "@/hooks/use-admin-guard";
import { AdminShell } from "@/components/admin/AdminShell";

const mockedGuard = vi.mocked(useAdminGuard);

describe("AdminShell", () => {
  it("shows a loading message while the guard is checking permissions", () => {
    mockedGuard.mockReturnValue({ status: "loading" });
    render(<AdminShell>page content</AdminShell>);
    expect(screen.getByText("Verificando permissões…")).toBeInTheDocument();
  });

  it("shows the access-restricted screen when the guard denies", () => {
    mockedGuard.mockReturnValue({ status: "denied" });
    render(<AdminShell>page content</AdminShell>);
    expect(screen.getByText("Acesso restrito")).toBeInTheDocument();
    expect(screen.queryByText("page content")).not.toBeInTheDocument();
  });

  it("renders the sidebar, header and page content when the guard allows", () => {
    mockedGuard.mockReturnValue({
      status: "ok",
      user: { id: 1, email: "admin@dario.os", full_name: "Admin", role: "admin", is_active: true },
    });
    render(<AdminShell>page content</AdminShell>);
    expect(screen.getByText("page content")).toBeInTheDocument();
    expect(screen.getByText("admin@dario.os")).toBeInTheDocument();
    expect(screen.getByText("Dashboard")).toBeInTheDocument(); // sidebar item
  });
});
