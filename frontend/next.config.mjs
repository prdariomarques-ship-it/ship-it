import createBundleAnalyzer from "@next/bundle-analyzer";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
};

// Opt-in only (`ANALYZE=true npm run build`) — no effect on a normal build,
// dev server, or production behavior.
const withBundleAnalyzer = createBundleAnalyzer({ enabled: process.env.ANALYZE === "true" });

export default withBundleAnalyzer(nextConfig);
