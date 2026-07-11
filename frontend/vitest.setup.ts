import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";

// Explicit cleanup between tests: this project imports `describe`/`it` from
// "vitest" rather than enabling Vitest's `globals` option, so
// @testing-library/react's own auto-cleanup (which hooks the *global*
// `afterEach`) never registers — without this, each test's rendered tree
// stays mounted and accumulates into the next test's `document.body`.
afterEach(() => {
  cleanup();
});

// jsdom has no ResizeObserver — Recharts' <ResponsiveContainer> needs one to
// mount at all. A no-op stub is enough for component tests that don't
// assert on actual pixel dimensions.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverStub;
