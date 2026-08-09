import "server-only";

import { NextResponse } from "next/server";

import { getOperatorSecurityStatus } from "@/lib/server/operator-security";

export type OperatorApiAccessRequirement = "AUTHENTICATED" | "OPERATOR" | "ADMIN";

function noStoreJson(
  body: Record<string, unknown>,
  status: number,
): NextResponse {
  return NextResponse.json(body, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

export async function requireOperatorApiAccess(
  requirement: OperatorApiAccessRequirement,
): Promise<NextResponse | null> {
  const operator = await getOperatorSecurityStatus();

  if (!operator) {
    return noStoreJson(
      {
        success: false,
        code: "OPERATOR_SECURITY_UNAVAILABLE",
        message: "운영자 권한 상태를 확인할 수 없습니다.",
      },
      503,
    );
  }

  if (!operator.enabled) {
    return null;
  }

  if (!operator.authenticated) {
    return noStoreJson(
      {
        success: false,
        code: "OPERATOR_AUTHENTICATION_REQUIRED",
        message: "이 작업에는 운영자 로그인이 필요합니다.",
      },
      401,
    );
  }

  if (
    requirement === "OPERATOR" &&
    operator.role !== "OPERATOR" &&
    operator.role !== "ADMIN"
  ) {
    return noStoreJson(
      {
        success: false,
        code: "OPERATOR_PERMISSION_DENIED",
        message: "이 작업에는 OPERATOR 이상의 권한이 필요합니다.",
      },
      403,
    );
  }

  if (
    requirement === "ADMIN" &&
    operator.role !== "ADMIN"
  ) {
    return noStoreJson(
      {
        success: false,
        code: "OPERATOR_ADMIN_REQUIRED",
        message: "이 작업에는 ADMIN 권한이 필요합니다.",
      },
      403,
    );
  }

  return null;
}
