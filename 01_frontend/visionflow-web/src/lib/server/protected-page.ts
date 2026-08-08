import "server-only";

import { redirect } from "next/navigation";

import { getOperatorAuthMode } from "@/lib/server/operator-auth";
import { getOperatorSecurityStatus } from "@/lib/server/operator-security";

type ProtectedSearchValue = string | string[] | undefined;

function safeReturnTo(returnTo: string): string {
  const candidate = returnTo.trim();
  return candidate.startsWith("/") && !candidate.startsWith("//")
    ? candidate
    : "/dashboard";
}

export function buildProtectedReturnTo(
  pathname: string,
  searchParams: Record<string, ProtectedSearchValue>,
): string {
  const params = new URLSearchParams();

  for (const [key, value] of Object.entries(searchParams)) {
    if (Array.isArray(value)) {
      for (const item of value) {
        params.append(key, item);
      }
    } else if (typeof value === "string") {
      params.set(key, value);
    }
  }

  const search = params.toString();
  return search ? `${pathname}?${search}` : pathname;
}

export async function requireOperatorAuthentication(
  returnTo: string,
): Promise<void> {
  if (getOperatorAuthMode() !== "session") {
    return;
  }

  const status = await getOperatorSecurityStatus();
  if (status?.enabled === true && status.authenticated === false) {
    redirect(
      `/operator-login?returnTo=${encodeURIComponent(safeReturnTo(returnTo))}`,
    );
  }
}
