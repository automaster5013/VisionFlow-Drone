import "server-only";

import { NextResponse } from "next/server";

import { withBackendOperatorAuth } from "@/lib/server/operator-auth";
import {
  parseOperatorSessions,
  type OperatorManagedSession,
} from "@/types/operator-session-management";

const BACKEND_API_URL = (
  process.env.SPRING_API_URL ??
  process.env.BACKEND_API_URL ??
  process.env.API_BASE_URL ??
  "http://localhost:8080"
).replace(/\/$/, "");

function errorMessage(value: unknown, fallback: string): string {
  return typeof value === "object" &&
    value !== null &&
    "message" in value &&
    typeof value.message === "string"
    ? value.message
    : fallback;
}

export async function getOperatorSessions(): Promise<OperatorManagedSession[]> {
  const response = await fetch(
    `${BACKEND_API_URL}/api/security/sessions`,
    await withBackendOperatorAuth({
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(5_000),
    }),
  );
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(errorMessage(body, "활성 운영자 세션을 조회할 수 없습니다."));
  }
  const sessions = parseOperatorSessions(body);
  if (!sessions) {
    throw new Error("활성 운영자 세션 응답 형식이 올바르지 않습니다.");
  }
  return sessions;
}

export async function proxyOperatorSessionRequest(
  backendPath: string,
  method: "GET" | "DELETE",
): Promise<NextResponse> {
  try {
    const response = await fetch(
      `${BACKEND_API_URL}${backendPath}`,
      await withBackendOperatorAuth({
        method,
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: AbortSignal.timeout(5_000),
      }),
    );
    const body = await response.text();
    return new NextResponse(body || null, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    console.error("운영자 세션 관리 프록시 오류:", error);
    return NextResponse.json(
      {
        success: false,
        code: "BACKEND_UNAVAILABLE",
        message: "백엔드 운영자 세션 관리 API에 연결할 수 없습니다.",
      },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
