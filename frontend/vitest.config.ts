import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Scoped to the admin dashboard (Sprint 4) — the only part of this frontend
// with a component test suite so far; existing pages had none before this
// sprint and this config doesn't change that.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
    css: false,
    coverage: {
      provider: "v8",
      reporter: ["text", "text-summary"],
      include: [
        "components/admin/**/*.{ts,tsx}",
        "lib/**/*.{ts,tsx}",
        "hooks/**/*.{ts,tsx}",
      ],
      exclude: [
        "components/admin/ui/**", // hand-authored shadcn/ui primitives, not app logic
        "hooks/useApi.ts", // pre-existing (Fase 4), unmodified by Sprint 4 — out of scope
      ],
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});
