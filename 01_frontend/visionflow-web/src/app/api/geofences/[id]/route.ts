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

async function resolveBackendUrl(
  context: RouteContext,
): Promise<string | null> {
  const { id } = await context.params;

  if (!/^\d+$/.test(id)) {
    return null;
  }

  return `${BACKEND_API_URL}/api/geofences/${encodeURIComponent(id)}`;
}

async function forwardToBackend(
  backendUrl: string,
  init: RequestInit,
): Promise<NextResponse> {
  try {
    const response = await fetch(
      backendUrl,
      await withBackendOperatorAuth(init),
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
    console.error("지오펜스 상세 프록시 오류:", error);

    return NextResponse.json(
      {
        message: "백엔드 지오펜스 API에 연결할 수 없습니다.",
      },
      { status: 502 },
    );
  }
}

export async function GET(_request: NextRequest, context: RouteContext) {
  const backendUrl = await resolveBackendUrl(context);

  if (!backendUrl) {
    return NextResponse.json(
      { message: "잘못된 지오펜스 ID입니다." },
      { status: 400 },
    );
  }

  return forwardToBackend(backendUrl, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    cache: "no-store",
  });
}

export async function PUT(request: NextRequest, context: RouteContext) {
  const rejected = rejectCrossOriginOperatorMutation(request);
  if (rejected) {
    return rejected;
  }

  const backendUrl = await resolveBackendUrl(context);

  if (!backendUrl) {
    return NextResponse.json(
      { message: "잘못된 지오펜스 ID입니다." },
      { status: 400 },
    );
  }

  return forwardToBackend(backendUrl, {
    method: "PUT",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: await request.text(),
    cache: "no-store",
  });
}
