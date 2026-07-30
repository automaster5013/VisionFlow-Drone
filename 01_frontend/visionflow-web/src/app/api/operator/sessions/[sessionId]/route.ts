import { type NextRequest, NextResponse } from "next/server";

import { proxyOperatorSessionRequest } from "@/lib/server/operator-session-management";
import { isSameOriginRequest } from "@/lib/server/same-origin";

interface RouteContext {
  params: Promise<{ sessionId: string }>;
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export async function DELETE(request: NextRequest, context: RouteContext) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json(
      {
        success: false,
        code: "CROSS_ORIGIN_SESSION_REVOKE_DENIED",
        message: "다른 출처에서 운영자 세션을 종료할 수 없습니다.",
      },
      { status: 403 },
    );
  }

  const { sessionId } = await context.params;
  if (!UUID_PATTERN.test(sessionId)) {
    return NextResponse.json(
      { message: "운영자 세션 ID 형식이 올바르지 않습니다." },
      { status: 400 },
    );
  }

  return proxyOperatorSessionRequest(
    `/api/security/sessions/${encodeURIComponent(sessionId)}`,
    "DELETE",
  );
}
