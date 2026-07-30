import "server-only";

import { type NextRequest, NextResponse } from "next/server";

import {
  getOperatorAuthMode,
  OPERATOR_SESSION_COOKIE,
} from "@/lib/server/operator-auth";
import { isSameOriginRequest } from "@/lib/server/same-origin";

export function rejectCrossOriginOperatorMutation(
  request: NextRequest,
): NextResponse | null {
  if (getOperatorAuthMode() !== "session") {
    return null;
  }

  const sessionCookie = request.cookies
    .get(OPERATOR_SESSION_COOKIE)
    ?.value.trim();
  if (!sessionCookie) {
    return null;
  }

  const fetchSite = request.headers
    .get("sec-fetch-site")
    ?.trim()
    .toLowerCase();
  const hasOrigin = request.headers.has("origin");
  const trusted =
    (!fetchSite || fetchSite === "same-origin") &&
    (!hasOrigin || isSameOriginRequest(request)) &&
    (fetchSite === "same-origin" || hasOrigin);

  if (trusted) {
    return null;
  }

  return NextResponse.json(
    {
      success: false,
      code: "CROSS_ORIGIN_MUTATION_DENIED",
      message: "다른 출처에서 운영 변경 요청을 실행할 수 없습니다.",
      errors: {},
      timestamp: new Date().toISOString(),
    },
    {
      status: 403,
      headers: { "Cache-Control": "no-store" },
    },
  );
}
