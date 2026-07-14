/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  compiler: {
    removeConsole: process.env.NODE_ENV === "production",
  },
  env: {
    NEXT_PUBLIC_RUNTIME_API: process.env.NEXT_PUBLIC_RUNTIME_API || "http://localhost:5000",
  },
};

module.exports = nextConfig;
