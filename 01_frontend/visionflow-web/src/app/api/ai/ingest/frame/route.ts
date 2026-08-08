import { type NextRequest, NextResponse } from "next/server";

import { withAiInternalAuth } from "@/lib/server/ai-internal-auth";
import { requireOperatorApiAccess } from "@/lib/server/operator-api-access";
import { isSameOriginRequest } from "@/lib/server/same-origin";

const AI_STREAM_API_URL = (
  process.env.AI_STREAM_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

const MAX_FRAME_BYTES = 2_000_000;

function badRequest(message: string) {
  return NextResponse.json(
    { message },
    {
      status: 400,
      headers: { "Cache-Control": "no-store" },
    },
  );
}

export async function POST(request: NextRequest) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json(
      {
        success: false,
        code: "CROSS_ORIGIN_AI_FRAME_INGEST_DENIED",
        message: "다른 출처에서 AI 영상 프레임을 전송할 수 없습니다.",
      },
      { status: 403, headers: { "Cache-Control": "no-store" } },
    );
  }

  const access = await requireOperatorApiAccess("OPERATOR");
  if (access) {
    return access;
  }

  const droneId = request.nextUrl.searchParams.get("droneId") ?? "";
  const sourceId = request.nextUrl.searchParams.get("sourceId")?.trim() ?? "";
  const sessionId = request.nextUrl.searchParams.get("sessionId")?.trim() ?? "";
  const capturedAt = request.nextUrl.searchParams.get("capturedAt") ?? "";

  if (!/^\d+$/.test(droneId) || Number(droneId) <= 0) {
    return badRequest("잘못된 드론 ID입니다.");
  }

  if (sourceId.length < 1 || sourceId.length > 100) {
    return badRequest("영상 소스 ID는 1~100자여야 합니다.");
  }

  if (sessionId.length < 1 || sessionId.length > 36) {
    return badRequest("영상 세션 ID는 1~36자여야 합니다.");
  }

  if (capturedAt && Number.isNaN(new Date(capturedAt).getTime())) {
    return badRequest("촬영 시각 형식이 올바르지 않습니다.");
  }

  const contentType = request.headers.get("content-type")?.split(";", 1)[0];

  if (contentType !== "image/jpeg") {
    return NextResponse.json(
      { message: "Content-Type은 image/jpeg여야 합니다." },
      {
        status: 415,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }

  const body = await request.arrayBuffer();

  if (body.byteLength === 0) {
    return badRequest("JPEG 프레임이 비어 있습니다.");
  }

  if (body.byteLength > MAX_FRAME_BYTES) {
    return NextResponse.json(
      { message: "JPEG 프레임 용량 제한을 초과했습니다." },
      {
        status: 413,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }

  const upstreamQuery = new URLSearchParams({
    droneId,
    sourceId,
    sessionId,
  });

  if (capturedAt) {
    upstreamQuery.set("capturedAt", capturedAt);
  }

  try {
    const response = await fetch(
      `${AI_STREAM_API_URL}/api/ingest/frame?${upstreamQuery.toString()}`,
      withAiInternalAuth({
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "image/jpeg",
        },
        body,
        cache: "no-store",
        signal: AbortSignal.timeout(5_000),
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
    console.error("AI 브라우저 영상 프레임 프록시 오류:", error);

    return NextResponse.json(
      { message: "AI 영상 입력 서버에 연결할 수 없습니다." },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}
