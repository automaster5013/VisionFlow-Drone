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

async function validatedPath(context: RouteContext) {
  const { id, sessionId: rawSessionId } = await context.params;
  const sessionId = rawSessionId.trim();

  if (!/^\d+$/.test(id) || Number(id) <= 0) {
    return { error: badRequest("잘못된 드론 ID입니다.") };
  }

  if (sessionId.length < 1 || sessionId.length > 36) {
    return {
      error: badRequest("비행 세션 ID는 1~36자여야 합니다."),
    };
  }

  return { id, sessionId };
}

async function proxyQualityAssessment(
  id: string,
  sessionId: string,
  method: "GET" | "PUT",
) {
  try {
    const response = await fetch(
      `${BACKEND_API_URL}/api/drones/${encodeURIComponent(id)}` +
        `/flight-sessions/${encodeURIComponent(sessionId)}` +
        "/quality-assessment",
      await withBackendOperatorAuth({
        method,
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: AbortSignal.timeout(15_000),
      }),
    );
    const body = await response.text();

    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    console.error(`비행 품질 평가 ${method} 프록시 오류:`, error);

    return NextResponse.json(
      { message: "백엔드 비행 품질 평가 API에 연결할 수 없습니다." },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}

export async function GET(_request: NextRequest, context: RouteContext) {
  const path = await validatedPath(context);

  return "error" in path
    ? path.error
    : proxyQualityAssessment(path.id, path.sessionId, "GET");
}

export async function PUT(request: NextRequest, context: RouteContext) {
  const rejected = rejectCrossOriginOperatorMutation(request);
  if (rejected) {
    return rejected;
  }

  const path = await validatedPath(context);

  return "error" in path
    ? path.error
    : proxyQualityAssessment(path.id, path.sessionId, "PUT");
}
