import "server-only";

import { type NextRequest, NextResponse } from "next/server";

import {
  OPERATOR_SESSION_COOKIE,
  withBackendOperatorAuth,
} from "@/lib/server/operator-auth";

const BACKEND_API_URL = (
  process.env.SPRING_API_URL ??
  process.env.BACKEND_API_URL ??
  process.env.API_BASE_URL ??
  "http://localhost:8080"
).replace(/\/$/, "");

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

interface BackendOperatorSession {
  token: string;
  username: string;
  role: string;
  expiresAt: string;
}

function isBackendOperatorSession(
  value: unknown,
): value is BackendOperatorSession {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Partial<BackendOperatorSession>;
  return (
    typeof candidate.token === "string" &&
    candidate.token.length >= 40 &&
    typeof candidate.username === "string" &&
    typeof candidate.role === "string" &&
    typeof candidate.expiresAt === "string" &&
    Number.isFinite(Date.parse(candidate.expiresAt))
  );
}

export function isOperatorPairingId(value: string): boolean {
  return UUID_PATTERN.test(value);
}

interface ProxyOptions {
  authenticated: boolean;
  issueBrowserSession?: boolean;
}

export async function proxyOperatorPairingRequest(
  request: NextRequest,
  backendPath: string,
  method: "GET" | "POST" | "DELETE",
  options: ProxyOptions,
): Promise<NextResponse> {
  try {
    const body = method === "POST" ? await request.text() : "";
    const init: RequestInit = {
      method,
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body || undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(5_000),
    };
    const backendInit = options.authenticated
      ? await withBackendOperatorAuth(init)
      : init;
    const response = await fetch(
      `${BACKEND_API_URL}${backendPath}`,
      backendInit,
    );
    const responseText = await response.text();

    if (options.issueBrowserSession && response.ok) {
      let parsed: unknown = null;

      try {
        parsed = responseText ? JSON.parse(responseText) : null;
      } catch {
        parsed = null;
      }

      if (!isBackendOperatorSession(parsed)) {
        return NextResponse.json(
          {
            success: false,
            code: "INVALID_OPERATOR_PAIRING_SESSION_RESPONSE",
            message: "페어링 세션 응답 형식이 올바르지 않습니다.",
          },
          { status: 502 },
        );
      }

      const nextResponse = NextResponse.json({
        authenticated: true,
        username: parsed.username,
        role: parsed.role,
        expiresAt: parsed.expiresAt,
      });
      nextResponse.cookies.set({
        name: OPERATOR_SESSION_COOKIE,
        value: parsed.token,
        httpOnly: true,
        sameSite: "lax",
        secure:
          process.env.VISIONFLOW_WEB_SECURE_COOKIES
            ?.trim()
            .toLowerCase() === "true",
        path: "/",
        expires: new Date(parsed.expiresAt),
      });
      nextResponse.headers.set("Cache-Control", "no-store");
      return nextResponse;
    }

    return new NextResponse(responseText || null, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    console.error("운영자 QR 페어링 프록시 오류:", error);
    return NextResponse.json(
      {
        success: false,
        code: "BACKEND_UNAVAILABLE",
        message: "백엔드 운영자 QR 페어링 API에 연결할 수 없습니다.",
      },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}
