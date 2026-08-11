import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Required for Dockerfile.frontend multi-stage runner image.
  output: "standalone",
};

export default nextConfig;
