/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "coin-images.coingecko.com",
      },
    ],
  },
  async rewrites() {
    return [
      // Per-asset market data routes (also support direct /api/mutual, /api/stock, /api/crypto)
      // Note: /api/backend/* routes are handled by Next.js route handlers in /app/api/backend/*/route.js
      // They are NOT rewritten here so they can add auth headers before calling the backend
      {
        source: "/api/mutual/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL}/api/mutual/:path*`,
      },
      {
        source: "/api/stock/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL}/api/stock/:path*`,
      },
      {
        source: "/api/crypto/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL}/api/crypto/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
