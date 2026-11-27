import type { NextConfig } from "next";

// Django serves the API, Africa's Talking webhooks, the admin and uploaded media. Proxying them
// through Next.js gives the browser a single origin (session cookie + CSRF), and one public tunnel
// (ngrok / cloudflared) on port 3000 exposes both the website and the AT callback URLs.
const BACKEND = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

// Security headers for the pages Next.js serves (Django sets its own on the proxied API and admin).
// Production only: `next dev` needs eval and websockets, and editor previews frame the dev site.
// Next's inline bootstrap scripts need 'unsafe-inline'; photos and map tiles come from https origins,
// photo previews are blob: URLs and voicemail plays from Africa's Talking's https recording links.
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "media-src 'self' https:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");
const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: CSP },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
];

const nextConfig: NextConfig = {
  output: "standalone", // slim Docker image (frontend/Dockerfile)
  poweredByHeader: false,
  cacheComponents: true,
  partialPrefetching: true,
  skipTrailingSlashRedirect: true, // Django admin uses trailing slashes; AT callbacks must never be redirected
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  images: {
    remotePatterns: [{ protocol: "https", hostname: "images.unsplash.com" }],
  },
  async headers() {
    if (process.env.NODE_ENV !== "production") return [];
    // everything except the paths proxied to Django, which answers with its own headers
    return [{ source: "/((?!api/|at/|media/|admin/|static/|health$).*)", headers: SECURITY_HEADERS }];
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
      { source: "/at/:path*", destination: `${BACKEND}/at/:path*` },
      { source: "/media/:path*", destination: `${BACKEND}/media/:path*` },
      // the admin's URLs end in "/", which `:path*` drops (Django would then bounce between login redirects)
      { source: "/admin", destination: `${BACKEND}/admin/` },
      { source: "/admin/:path*/", destination: `${BACKEND}/admin/:path*/` },
      { source: "/admin/:path*", destination: `${BACKEND}/admin/:path*` },
      { source: "/static/:path*", destination: `${BACKEND}/static/:path*` },
      { source: "/health", destination: `${BACKEND}/health` },
    ];
  },
};

export default nextConfig;
