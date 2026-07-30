import "server-only";

import {
  getOperatorAuthMode,
  withBackendOperatorAuth,
} from "@/lib/server/operator-auth";
import type { OperatorSecurityStatus } from "@/types/operator-security";

const BACKEND_API_URL = (
  process.env.SPRING_API_URL ??
  process.env.BACKEND_API_URL ??
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8080"
).replace(/\/$/, "");

export async function getOperatorSecurityStatus(): Promise<OperatorSecurityStatus | null> {
  try {
    const response = await fetch(
      `${BACKEND_API_URL}/api/security/me`,
      await withBackendOperatorAuth({
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: AbortSignal.timeout(3_000),
      }),
    );

    if (response.status === 401) {
      return {
        enabled: true,
        authenticated: false,
        username: null,
        role:
          getOperatorAuthMode() === "session"
            ? "INVALID_SESSION"
            : "INVALID_KEY",
      };
    }

    if (!response.ok) {
      return null;
    }

    return (await response.json()) as OperatorSecurityStatus;
  } catch {
    return null;
  }
}
