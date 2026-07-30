import { type NextRequest, NextResponse } from "next/server";

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

export async function GET(_request: NextRequest, context: RouteContext) {
  const { id } = await context.params;

  if (!/^\d+$/.test(id)) {
    return NextResponse.json(
      { message: "잘못된 AI 이벤트 ID입니다." },
      { status: 400 },
    );
  }

  try {
    const response = await fetch(
      `${BACKEND_API_URL}/api/ai/events/${encodeURIComponent(id)}/snapshot`,
      {
        method: "GET",
        headers: {
          Accept: "image/jpeg",
        },
        cache: "no-store",
      },
    );

    const body = await response.arrayBuffer();

    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Content-Type":
          response.headers.get("content-type") ?? "application/octet-stream",
        ...(response.headers.get("content-disposition")
          ? {
              "Content-Disposition": response.headers.get(
                "content-disposition",
              )!,
            }
          : {}),
      },
    });
  } catch (error) {
    console.error("AI 이벤트 스냅샷 프록시 오류:", error);

    return NextResponse.json(
      {
        message: "백엔드 AI 이벤트 스냅샷 API에 연결할 수 없습니다.",
      },
      { status: 502 },
    );
  }
}
