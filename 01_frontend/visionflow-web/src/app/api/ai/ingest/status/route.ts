import { NextResponse } from "next/server";

const AI_STREAM_API_URL = (
  process.env.AI_STREAM_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export async function GET() {
  try {
    const response = await fetch(`${AI_STREAM_API_URL}/api/ingest/status`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(2_000),
    });

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
    console.error("AI 브라우저 영상 입력 상태 프록시 오류:", error);

    return NextResponse.json(
      { message: "AI 영상 입력 서버에 연결할 수 없습니다." },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}
