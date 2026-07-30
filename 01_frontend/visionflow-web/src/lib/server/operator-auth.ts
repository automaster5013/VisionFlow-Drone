import "server-only";

import { cookies } from "next/headers";

import type { OperatorAuthMode } from "@/types/operator-security";

export const OPERATOR_KEY_HEADER = "X-VisionFlow-Operator-Key";
export const OPERATOR_SESSION_HEADER = "X-VisionFlow-Operator-Session";
export const OPERATOR_SESSION_COOKIE = "visionflow_operator_session";

export function getOperatorAuthMode(): OperatorAuthMode {
  return process.env.VISIONFLOW_WEB_AUTH_MODE?.trim().toLowerCase() === "session"
    ? "session"
    : "static";
}

export async function withBackendOperatorAuth(
  init: RequestInit = {},
): Promise<RequestInit> {
  const headers = new Headers(init.headers);
  headers.delete(OPERATOR_KEY_HEADER);
  headers.delete(OPERATOR_SESSION_HEADER);

  if (getOperatorAuthMode() === "session") {
    const cookieStore = await cookies();
    const operatorSession = cookieStore
      .get(OPERATOR_SESSION_COOKIE)
      ?.value.trim();

    if (operatorSession) {
      headers.set(OPERATOR_SESSION_HEADER, operatorSession);
    }
  } else {
    const operatorKey = (
      process.env.VISIONFLOW_WEB_OPERATOR_KEY ??
      process.env.VISIONFLOW_OPERATOR_KEY
    )?.trim();

    if (operatorKey) {
      headers.set(OPERATOR_KEY_HEADER, operatorKey);
    }
  }

  return {
    ...init,
    headers,
  };
}
