import { render, screen } from "@testing-library/react";
import { useRef } from "react";
import { describe, expect, it } from "vitest";

import { PortalContainerProvider, usePortalContainer } from "@/hooks/use-portal-container";

function Consumer() {
  const container = usePortalContainer();
  return <div data-testid="result">{container ? "has-container" : "no-container"}</div>;
}

describe("usePortalContainer", () => {
  it("returns undefined outside any provider", () => {
    render(<Consumer />);
    expect(screen.getByTestId("result")).toHaveTextContent("no-container");
  });

  it("returns the ref's current node once the provider has mounted", () => {
    function Wrapper() {
      const ref = useRef<HTMLDivElement>(null);
      return (
        <div ref={ref} className="admin-theme">
          <PortalContainerProvider containerRef={ref}>
            <Consumer />
          </PortalContainerProvider>
        </div>
      );
    }
    render(<Wrapper />);
    expect(screen.getByTestId("result")).toHaveTextContent("has-container");
  });
});
