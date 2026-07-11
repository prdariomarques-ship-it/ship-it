import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AdminToastProvider, useToast } from "@/hooks/use-toast";

function Trigger() {
  const { toast } = useToast();
  return (
    <button onClick={() => toast({ title: "Falha", description: "algo deu errado", variant: "destructive" })}>
      fire
    </button>
  );
}

describe("AdminToastProvider / useToast", () => {
  it("renders a toast with title and description after toast() is called", async () => {
    render(
      <AdminToastProvider>
        <Trigger />
      </AdminToastProvider>
    );
    await userEvent.click(screen.getByText("fire"));
    expect(await screen.findByText("Falha")).toBeInTheDocument();
    expect(screen.getByText("algo deu errado")).toBeInTheDocument();
  });

  it("throws when useToast is used outside the provider", () => {
    const Bare = () => {
      useToast();
      return null;
    };
    // Suppress the expected React error boundary console noise for this assertion.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Bare />)).toThrow("useToast must be used within AdminToastProvider");
    spy.mockRestore();
  });
});
