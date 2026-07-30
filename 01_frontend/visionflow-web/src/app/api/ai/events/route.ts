import { type NextRequest, NextResponse } from "next/server";

const BACKEND_API_URL = (
  process.env.BACKEND_API_URL ??
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8080"
).replace(/\/$/, "");

export async function GET(request: NextRequest) {
  try {
    const backendUrl = new URL(`${BACKEND_API_URL}/api/ai/events`);

    backendUrl.search = request.nextUrl.search;

    const response = await fetch(backendUrl, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      cache: "no-store",
    });

    const body = await response.text();

    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (error) {
    console.error("AI 추론 이벤트 프록시 오류:", error);

    return NextResponse.json(
      {
        message: "백엔드 AI 추론 이벤트 API에 연결할 수 없습니다.",
      },
      { status: 502 },
    );
  }
}
