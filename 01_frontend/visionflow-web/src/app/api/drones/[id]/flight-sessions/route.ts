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

function parseLimit(value: string | null): number | null {
  if (value === null) {
    return 20;
  }

  if (!/^\d+$/.test(value)) {
    return null;
  }

  const parsed = Number(value);

  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 100
    ? parsed
    : null;
}

export async function GET(request: NextRequest, context: RouteContext) {
  const { id } = await context.params;

  if (!/^\d+$/.test(id) || Number(id) <= 0) {
    return badRequest("잘못된 드론 ID입니다.");
  }

  const limit = parseLimit(request.nextUrl.searchParams.get("limit"));
  const query = (request.nextUrl.searchParams.get("query") ?? "").trim();

  if (limit === null) {
    return badRequest("세션 조회 제한값은 1~100이어야 합니다.");
  }

  if (query.length > 36) {
    return badRequest("세션 검색어는 36자 이하여야 합니다.");
  }

  const upstreamQuery = new URLSearchParams({ limit: String(limit) });

  if (query) {
    upstreamQuery.set("query", query);
  }

  try {
    const response = await fetch(
      `${BACKEND_API_URL}/api/drones/${encodeURIComponent(id)}` +
        `/flight-sessions?${upstreamQuery}`,
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
    console.error("비행 세션 목록 프록시 오류:", error);

    return NextResponse.json(
      { message: "백엔드 비행 세션 목록 API에 연결할 수 없습니다." },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
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

  const body = await request.text();

  if (body.length > 2_000) {
    return NextResponse.json(
      { message: "비행 세션 시작 요청이 너무 큽니다." },
      {
        status: 413,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }

  try {
    const response = await fetch(
      `${BACKEND_API_URL}/api/drones/${encodeURIComponent(id)}` +
        "/flight-sessions",
      await withBackendOperatorAuth({
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: body || "{}",
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
    console.error("비행 세션 시작 프록시 오류:", error);

    return NextResponse.json(
      { message: "백엔드 비행 세션 시작 API에 연결할 수 없습니다." },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}
