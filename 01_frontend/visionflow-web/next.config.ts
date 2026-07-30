import type { NextConfig } from "next";

function isValidIpv4(value: string): boolean {
  const segments = value.split(".");

  return (
    segments.length === 4 &&
    segments.every(
      (segment) =>
        /^(?:0|[1-9]\d{0,2})$/.test(segment) &&
        Number(segment) <= 255,
    )
  );
}

const requestedMobileLanIp =
  process.env.VISIONFLOW_MOBILE_LAN_IP?.trim() ?? "";
const mobileLanIp = isValidIpv4(requestedMobileLanIp)
  ? requestedMobileLanIp
  : null;
const mobileHttpsConnectSources = mobileLanIp
  ? [`https://${mobileLanIp}:3000`, `wss://${mobileLanIp}:3000`]
  : [];

const contentSecurityPolicyReportOnly = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "frame-src 'none'",
  "form-action 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://*.tile.openstreetmap.org",
  "media-src 'self' blob:",
  "font-src 'self' data:",
  "worker-src 'self' blob:",
  [
    "connect-src 'self'",
    "http://localhost:*",
    "http://127.0.0.1:*",
    "ws://localhost:*",
    "ws://127.0.0.1:*",
    ...mobileHttpsConnectSources,
  ].join(" "),
  "manifest-src 'self'",
  "report-uri /api/security/csp-report",
].join("; ");

const securityHeaders = [
  {
    key: "X-Content-Type-Options",
    value: "nosniff",
  },
  {
    key: "X-Frame-Options",
    value: "DENY",
  },
  {
    key: "Referrer-Policy",
    value: "strict-origin-when-cross-origin",
  },
  {
    key: "Permissions-Policy",
    value: "camera=(self), geolocation=(self), microphone=()",
  },
  {
    key: "Cross-Origin-Opener-Policy",
    value: "same-origin",
  },
  {
    key: "X-DNS-Prefetch-Control",
    value: "off",
  },
  {
    key: "X-Permitted-Cross-Domain-Policies",
    value: "none",
  },
  {
    key: "Content-Security-Policy-Report-Only",
    value: contentSecurityPolicyReportOnly,
  },
];

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  allowedDevOrigins: mobileLanIp ? [mobileLanIp] : [],
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
