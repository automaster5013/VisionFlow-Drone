import { NextResponse } from "next/server";

import { withAiInternalAuth } from "@/lib/server/ai-internal-auth";
import { requireOperatorApiAccess } from "@/lib/server/operator-api-access";

const AI_STREAM_API_URL = (
  process.env.AI_STREAM_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export const dynamic = "force-dynamic";

export async function GET() {
  const access = await requireOperatorApiAccess("AUTHENTICATED");
  if (access) {
    return access;
  }

  try {
    const response = await fetch(
      `${AI_STREAM_API_URL}/api/streams/annotated.mjpeg`,
      withAiInternalAuth({
        method: "GET",
        headers: { Accept: "multipart/x-mixed-replace" },
        cache: "no-store",
      }),
    );

    if (!response.ok || response.body === null) {
      const body = await response.text();

      return new NextResponse(body, {
        status: response.status,
        headers: {
          "Content-Type":
            response.headers.get("content-type") ?? "application/json",
          "Cache-Control": "no-store",
        },
      });
    }

    return new Response(response.body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") ??
          "multipart/x-mixed-replace; boundary=visionflow-frame",
        "Cache-Control": "no-store, no-cache, must-revalidate",
        Pragma: "no-cache",
      },
    });
  } catch (error) {
    console.error("AI 분석 영상 스트림 프록시 오류:", error);

    return NextResponse.json(
      { message: "AI 분석 영상 스트림 서버에 연결할 수 없습니다." },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}
