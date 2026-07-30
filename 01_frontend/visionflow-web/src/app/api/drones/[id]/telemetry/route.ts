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

export async function PATCH(request: NextRequest, context: RouteContext) {
  const { id } = await context.params;

  if (!/^\d+$/.test(id)) {
    return NextResponse.json(
      { message: "잘못된 드론 ID입니다." },
      { status: 400 },
    );
  }

  try {
    const response = await fetch(
      `${BACKEND_API_URL}/api/drones/${encodeURIComponent(id)}/telemetry`,
      {
        method: "PATCH",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: await request.text(),
        cache: "no-store",
      },
    );

    const body = await response.text();

    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (error) {
    console.error("드론 센서 텔레메트리 프록시 오류:", error);

    return NextResponse.json(
      {
        message: "백엔드 드론 텔레메트리 API에 연결할 수 없습니다.",
      },
      { status: 502 },
    );
  }
}
