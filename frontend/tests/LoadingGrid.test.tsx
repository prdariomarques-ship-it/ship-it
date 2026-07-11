import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LoadingGrid, LoadingRows } from "@/components/admin/LoadingGrid";

describe("LoadingGrid", () => {
  it("renders the requested number of skeleton tiles", () => {
    const { container } = render(<LoadingGrid count={4} />);
    expect(container.querySelectorAll(".animate-pulse-slow").length).toBe(4);
  });

  it("defaults to 6 tiles", () => {
    const { container } = render(<LoadingGrid />);
    expect(container.querySelectorAll(".animate-pulse-slow").length).toBe(6);
  });
});

describe("LoadingRows", () => {
  it("renders the requested number of skeleton rows", () => {
    const { container } = render(<LoadingRows count={3} />);
    expect(container.querySelectorAll(".animate-pulse-slow").length).toBe(3);
  });
});
