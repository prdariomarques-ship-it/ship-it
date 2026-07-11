import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AdminQueryProvider } from "@/components/admin/QueryProvider";

describe("AdminQueryProvider", () => {
  it("renders its children", () => {
    render(
      <AdminQueryProvider>
        <div>child content</div>
      </AdminQueryProvider>
    );
    expect(screen.getByText("child content")).toBeInTheDocument();
  });
});
