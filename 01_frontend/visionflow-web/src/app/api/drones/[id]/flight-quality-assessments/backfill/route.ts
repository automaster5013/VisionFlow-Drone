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
  params: Promise<{ id: string }>;
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

export async function POST(request: NextRequest, context: RouteContext) {
  const rejected = rejectCrossOriginOperatorMutation(request);
  if (rejected) {
    return rejected;
  }

  const { id } = await context.params;

  if (!/^\d+$/.test(id) || Number(id) <= 0) {
    return badRequest("잘못된 드론 ID입니다.");
  }

  const rawLimit = request.nextUrl.searchParams.get("limit") ?? "100";
  const rawForce = (
    request.nextUrl.searchParams.get("force") ?? "false"
  ).toLowerCase();

  if (!/^\d+$/.test(rawLimit)) {
    return badRequest("품질 평가 백필 제한값은 1~100이어야 합니다.");
  }

  const limit = Number(rawLimit);
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    return badRequest("품질 평가 백필 제한값은 1~100이어야 합니다.");
  }

  if (rawForce !== "true" && rawForce !== "false") {
    return badRequest("force 값은 true 또는 false여야 합니다.");
  }

  const query = new URLSearchParams({
    limit: String(limit),
    force: rawForce,
  });

  try {
    const response = await fetch(
      `${BACKEND_API_URL}/api/drones/${encodeURIComponent(id)}` +
        `/flight-quality-assessments/backfill?${query}`,
      await withBackendOperatorAuth({
        method: "POST",
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: AbortSignal.timeout(60_000),
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
    console.error("종료 비행 품질 평가 백필 프록시 오류:", error);

    return NextResponse.json(
      { message: "백엔드 품질 평가 백필 API에 연결할 수 없습니다." },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}
