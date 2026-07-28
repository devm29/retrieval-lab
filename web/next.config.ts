import type { NextConfig } from "next";

const apiUrl = process.env.RLAB_API_URL ?? "http://127.0.0.1:8102";

const nextConfig: NextConfig = {
  ...(process.env.NEXT_OUTPUT === "standalone" ? { output: "standalone" as const } : {}),
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
