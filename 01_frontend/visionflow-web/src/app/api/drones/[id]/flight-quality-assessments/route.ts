import { type NextRequest, NextResponse } from "next/server";

import { withBackendOperatorAuth } from "@/lib/server/operator-auth";

const BACKEND_API_URL = (
  process.env.BACKEND_API_URL ??
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8080"
).replace(/\/$/, "");

const ALLOWED_GRADES = new Set(["EXCELLENT", "GOOD", "CAUTION", "RISK"]);

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

export async function GET(request: NextRequest, context: RouteContext) {
  const { id } = await context.params;

  if (!/^\d+$/.test(id) || Number(id) <= 0) {
    return badRequest("잘못된 드론 ID입니다.");
  }

  const rawLimit = request.nextUrl.searchParams.get("limit") ?? "20";
  const grade = (request.nextUrl.searchParams.get("grade") ?? "")
    .trim()
    .toUpperCase();

  if (!/^\d+$/.test(rawLimit)) {
    return badRequest("품질 평가 조회 제한값은 1~100이어야 합니다.");
  }

  const limit = Number(rawLimit);
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    return badRequest("품질 평가 조회 제한값은 1~100이어야 합니다.");
  }

  if (grade && !ALLOWED_GRADES.has(grade)) {
    return badRequest("지원하지 않는 비행 품질 등급입니다.");
  }

  const query = new URLSearchParams({ limit: String(limit) });
  if (grade) {
    query.set("grade", grade);
  }

  try {
    const response = await fetch(
      `${BACKEND_API_URL}/api/drones/${encodeURIComponent(id)}` +
        `/flight-quality-assessments?${query}`,
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
    console.error("기체별 비행 품질 평가 이력 프록시 오류:", error);

    return NextResponse.json(
      { message: "백엔드 비행 품질 평가 이력 API에 연결할 수 없습니다." },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}
