import { type NextRequest, NextResponse } from "next/server";

import { withBackendOperatorAuth } from "@/lib/server/operator-auth";

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

function parseLimit(
  value: string | null,
  defaultValue: number,
  maximum: number,
): number | null {
  if (value === null) {
    return defaultValue;
  }

  if (!/^\d+$/.test(value)) {
    return null;
  }

  const parsed = Number(value);

  return Number.isInteger(parsed) && parsed >= 1 && parsed <= maximum
    ? parsed
    : null;
}

export async function GET(request: NextRequest, context: RouteContext) {
  const { id, sessionId: rawSessionId } = await context.params;
  const sessionId = rawSessionId.trim();

  if (!/^\d+$/.test(id) || Number(id) <= 0) {
    return badRequest("잘못된 드론 ID입니다.");
  }

  if (sessionId.length < 1 || sessionId.length > 36) {
    return badRequest("비행 세션 ID는 1~36자여야 합니다.");
  }

  const telemetryLimit = parseLimit(
    request.nextUrl.searchParams.get("telemetryLimit"),
    5_000,
    5_000,
  );
  const eventLimit = parseLimit(
    request.nextUrl.searchParams.get("eventLimit"),
    200,
    1_000,
  );

  if (telemetryLimit === null) {
    return badRequest("텔레메트리 제한값은 1~5000이어야 합니다.");
  }

  if (eventLimit === null) {
    return badRequest("AI 이벤트 제한값은 1~1000이어야 합니다.");
  }

  const query = new URLSearchParams({
    telemetryLimit: String(telemetryLimit),
    eventLimit: String(eventLimit),
  });

  try {
    const response = await fetch(
      `${BACKEND_API_URL}/api/drones/${encodeURIComponent(id)}` +
        `/flight-sessions/${encodeURIComponent(sessionId)}/replay?${query}`,
      await withBackendOperatorAuth({
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: AbortSignal.timeout(10_000),
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
    console.error("비행 세션 통합 리플레이 프록시 오류:", error);

    return NextResponse.json(
      { message: "백엔드 비행 세션 리플레이 API에 연결할 수 없습니다." },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}
