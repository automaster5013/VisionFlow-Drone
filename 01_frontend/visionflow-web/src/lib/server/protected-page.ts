import "server-only";

import { redirect } from "next/navigation";

import { getOperatorAuthMode } from "@/lib/server/operator-auth";
import { getOperatorSecurityStatus } from "@/lib/server/operator-security";
import type { OperatorSecurityStatus } from "@/types/operator-security";

type ProtectedSearchValue = string | string[] | undefined;

export type OperatorPageAccessRequirement =
  | "AUTHENTICATED"
  | "OPERATOR";

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


function hasRequiredPageAccess(
  status: OperatorSecurityStatus,
  requirement: OperatorPageAccessRequirement,
): boolean {
  if (!status.enabled) {
    return true;
  }

  if (!status.authenticated) {
    return false;
  }

  if (requirement === "AUTHENTICATED") {
    return true;
  }

  return status.role === "OPERATOR" || status.role === "ADMIN";
}

export async function requireOperatorPageAccess(
  returnTo: string,
  requirement: OperatorPageAccessRequirement,
): Promise<boolean> {
  const status = await getOperatorSecurityStatus();

  if (status && hasRequiredPageAccess(status, requirement)) {
    return true;
  }

  if (
    getOperatorAuthMode() === "session" &&
    status?.enabled === true &&
    status.authenticated === false
  ) {
    redirect(
      `/operator-login?returnTo=${encodeURIComponent(safeReturnTo(returnTo))}`,
    );
  }

  return false;
}
