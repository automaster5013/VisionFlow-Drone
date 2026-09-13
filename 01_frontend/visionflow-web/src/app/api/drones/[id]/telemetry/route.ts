import { type NextRequest, NextResponse } from "next/server";

import { requireOperatorApiAccess } from "@/lib/server/operator-api-access";
import { withBackendOperatorAuth } from "@/lib/server/operator-auth";
import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";
import { readBoundedMutationText } from "@/lib/server/bounded-request-body";
import { readBoundedRequestBody } from "@/lib/request-body-limit";

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
  const rejected = rejectCrossOriginOperatorMutation(request);
  if (rejected) {
    return rejected;
  }

  const access = await requireOperatorApiAccess("OPERATOR");
  if (access) {
    return access;
  }

  const { id } = await context.params;

  if (!/^\d+$/.test(id)) {
    return NextResponse.json(
      { message: "잘못된 드론 ID입니다." },
      { status: 400 },
    );
  }

  const parsedBody = await readBoundedMutationText(request, 64 * 1024, "텔레메트리 갱신");
  if (!parsedBody.ok) return parsedBody.response;

  try {
    const response = await fetch(
      `${BACKEND_API_URL}/api/drones/${encodeURIComponent(id)}/telemetry`,
      await withBackendOperatorAuth({
        method: "PATCH",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: parsedBody.body,
        cache: "no-store",
        signal: AbortSignal.timeout(10_000),
      }),
    );

    const responseBody = await readBoundedRequestBody(response.body, 64 * 1024);
    if (responseBody === null) {
      return NextResponse.json(
        { message: "백엔드 텔레메트리 응답이 허용 크기를 초과했습니다." },
        { status: 502, headers: { "Cache-Control": "no-store" } },
      );
    }
    const body = new TextDecoder().decode(responseBody);

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
