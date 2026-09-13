import { type NextRequest, NextResponse } from "next/server";

import { withBackendOperatorAuth } from "@/lib/server/operator-auth";
import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";
import { readBoundedTextRequest } from "@/lib/request-body-limit";

const MAX_GEOFENCE_REQUEST_BYTES = 1024 * 1024;

const BACKEND_API_URL = (
  process.env.BACKEND_API_URL ??
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8080"
).replace(/\/$/, "");

async function forwardToBackend(init: RequestInit): Promise<NextResponse> {
  try {
    const response = await fetch(
      `${BACKEND_API_URL}/api/geofences`,
      await withBackendOperatorAuth(init),
    );

    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    console.error("지오펜스 API 프록시 오류:", error);

    return NextResponse.json(
      {
        message: "백엔드 지오펜스 API에 연결할 수 없습니다.",
      },
      { status: 502 },
    );
  }
}

export async function GET() {
  return forwardToBackend({
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    cache: "no-store",
  });
}

export async function POST(request: NextRequest) {
  const rejected = rejectCrossOriginOperatorMutation(request);
  if (rejected) {
    return rejected;
  }

  const body = await readBoundedTextRequest(request, MAX_GEOFENCE_REQUEST_BYTES);
  if (!body.ok) {
    return NextResponse.json(
      { message: body.reason === "too_large" ? "지오펜스 요청이 허용 크기를 초과했습니다." : "지오펜스 요청 본문을 읽을 수 없습니다." },
      { status: body.reason === "too_large" ? 413 : 400, headers: { "Cache-Control": "no-store" } },
    );
  }

  return forwardToBackend({
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: body.value,
    cache: "no-store",
  });
}
