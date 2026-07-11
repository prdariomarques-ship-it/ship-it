import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EmptyState } from "@/components/admin/EmptyState";
import { ErrorState } from "@/components/admin/ErrorState";

describe("EmptyState", () => {
  it("renders title and optional description", () => {
    render(<EmptyState title="Nada por aqui" description="Ajuste os filtros." />);
    expect(screen.getByText("Nada por aqui")).toBeInTheDocument();
    expect(screen.getByText("Ajuste os filtros.")).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("renders the error message", () => {
    render(<ErrorState message="Network timeout" />);
    expect(screen.getByText("Network timeout")).toBeInTheDocument();
  });

  it("calls onRetry when the retry button is clicked", async () => {
    const onRetry = vi.fn();
    render(<ErrorState message="boom" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: /tentar novamente/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("renders no retry button when onRetry is not provided", () => {
    render(<ErrorState message="boom" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
