import { type NextRequest, NextResponse } from "next/server";

import { withBackendOperatorAuth } from "@/lib/server/operator-auth";
import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";

const BACKEND_API_URL = (
  process.env.BACKEND_API_URL ??
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8080"
).replace(/\/$/, "");

interface RouteContext {
  params: Promise<{
    id: string;
    sessionId: string;
  }>;
}

function badRequest(message: string) {
  return NextResponse.json(
    { message },
    {
      status: 400,
      headers: { "Cache-Control": "no-store" },
    },
  );
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  const rejected = rejectCrossOriginOperatorMutation(request);
  if (rejected) {
    return rejected;
  }

  const { id, sessionId: rawSessionId } = await context.params;
  const sessionId = rawSessionId.trim();

  if (!/^\d+$/.test(id) || Number(id) <= 0) {
    return badRequest("잘못된 드론 ID입니다.");
  }

  if (sessionId.length < 1 || sessionId.length > 36) {
    return badRequest("비행 세션 ID는 1~36자여야 합니다.");
  }

  const body = await request.text();

  if (body.length === 0) {
    return badRequest("수정할 비행 세션 정보를 입력해 주세요.");
  }

  if (body.length > 4_000) {
    return NextResponse.json(
      { message: "비행 세션 수정 요청이 너무 큽니다." },
      {
        status: 413,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }

  try {
    const response = await fetch(
      `${BACKEND_API_URL}/api/drones/${encodeURIComponent(id)}` +
        `/flight-sessions/${encodeURIComponent(sessionId)}`,
      await withBackendOperatorAuth({
        method: "PATCH",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body,
        cache: "no-store",
        signal: AbortSignal.timeout(10_000),
      }),
    );

    const responseBody = await response.text();

    return new NextResponse(responseBody, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    console.error("비행 세션 정보 수정 프록시 오류:", error);

    return NextResponse.json(
      { message: "백엔드 비행 세션 수정 API에 연결할 수 없습니다." },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}
