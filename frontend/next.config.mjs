import { fileURLToPath } from "node:url";
import createBundleAnalyzer from "@next/bundle-analyzer";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Pins the workspace root to this frontend/ directory. Without this,
  // Turbopack's auto-detection picks up the unrelated empty lockfile at
  // /home/dario/package-lock.json (outside this project) and misidentifies
  // the home directory as the root.
  turbopack: {
    root: fileURLToPath(new URL(".", import.meta.url)),
  },
};

// Opt-in only (`ANALYZE=true npm run build`) — no effect on a normal build,
// dev server, or production behavior.
const withBundleAnalyzer = createBundleAnalyzer({ enabled: process.env.ANALYZE === "true" });

export default withBundleAnalyzer(nextConfig);
