import { cookies } from "next/headers";
import { type NextRequest, NextResponse } from "next/server";

import {
  OPERATOR_SESSION_COOKIE,
  OPERATOR_SESSION_HEADER,
} from "@/lib/server/operator-auth";
import { isSameOriginRequest } from "@/lib/server/same-origin";

const BACKEND_API_URL = (
  process.env.SPRING_API_URL ??
  process.env.BACKEND_API_URL ??
  process.env.API_BASE_URL ??
  "http://localhost:8080"
).replace(/\/$/, "");

interface BackendOperatorSession {
  token: string;
  username: string;
  role: string;
  passwordChangeRequired: boolean;
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
    typeof candidate.passwordChangeRequired === "boolean" &&
    typeof candidate.expiresAt === "string" &&
    Number.isFinite(new Date(candidate.expiresAt).getTime())
  );
}

export async function POST(request: NextRequest) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json(
      {
        success: false,
        code: "CROSS_ORIGIN_PASSWORD_CHANGE_DENIED",
        message: "동일한 VisionFlow 화면에서 비밀번호를 변경하세요.",
      },
      { status: 403 },
    );
  }

  const body: unknown = await request.json().catch(() => null);
  const newPassword =
    typeof body === "object" &&
    body !== null &&
    "newPassword" in body &&
    typeof body.newPassword === "string"
      ? body.newPassword
      : "";
  if (newPassword.length < 15 || newPassword.length > 128) {
    return NextResponse.json(
      {
        success: false,
        code: "INVALID_OPERATOR_PASSWORD",
        message: "새 비밀번호는 15~128자로 입력하세요.",
      },
      { status: 400 },
    );
  }

  const cookieStore = await cookies();
  const token = cookieStore.get(OPERATOR_SESSION_COOKIE)?.value.trim();
  if (!token) {
    return NextResponse.json(
      {
        success: false,
        code: "OPERATOR_AUTHENTICATION_REQUIRED",
        message: "비밀번호를 변경하려면 다시 로그인하세요.",
      },
      { status: 401 },
    );
  }

  try {
    const backendResponse = await fetch(
      `${BACKEND_API_URL}/api/security/password`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          [OPERATOR_SESSION_HEADER]: token,
        },
        body: JSON.stringify({ newPassword }),
        cache: "no-store",
        signal: AbortSignal.timeout(5_000),
      },
    );
    const backendBody: unknown = await backendResponse.json().catch(() => null);
    if (!backendResponse.ok) {
      if (typeof backendBody === "object" && backendBody !== null) {
        return NextResponse.json(backendBody, { status: backendResponse.status });
      }
      return NextResponse.json(
        {
          success: false,
          code: "OPERATOR_PASSWORD_CHANGE_FAILED",
          message: "비밀번호를 변경하지 못했습니다.",
        },
        { status: backendResponse.status },
      );
    }
    if (!isBackendOperatorSession(backendBody)) {
      return NextResponse.json(
        {
          success: false,
          code: "INVALID_OPERATOR_SESSION_RESPONSE",
          message: "새 로그인 세션 응답 형식이 올바르지 않습니다.",
        },
        { status: 502 },
      );
    }

    const response = NextResponse.json({
      authenticated: true,
      username: backendBody.username,
      role: backendBody.role,
      passwordChangeRequired: backendBody.passwordChangeRequired,
      expiresAt: backendBody.expiresAt,
    });
    response.cookies.set({
      name: OPERATOR_SESSION_COOKIE,
      value: backendBody.token,
      httpOnly: true,
      sameSite: "lax",
      secure:
        process.env.VISIONFLOW_WEB_SECURE_COOKIES?.trim().toLowerCase() ===
        "true",
      path: "/",
      expires: new Date(backendBody.expiresAt),
    });
    response.headers.set("Cache-Control", "no-store");
    return response;
  } catch {
    return NextResponse.json(
      {
        success: false,
        code: "BACKEND_UNAVAILABLE",
        message: "백엔드 비밀번호 변경 서비스에 연결할 수 없습니다.",
      },
      { status: 503 },
    );
  }
}
