import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow reading from the parent directory's runtime/ for artifacts
  serverExternalPackages: [],
};

export default nextConfig;
