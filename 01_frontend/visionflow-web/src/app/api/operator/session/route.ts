import { cookies } from "next/headers";
import { type NextRequest, NextResponse } from "next/server";

import {
  getOperatorAuthMode,
  OPERATOR_KEY_HEADER,
  OPERATOR_SESSION_COOKIE,
  OPERATOR_SESSION_HEADER,
} from "@/lib/server/operator-auth";
import { getOperatorSecurityStatus } from "@/lib/server/operator-security";
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

async function readBody(response: Response): Promise<unknown> {
  return response.json().catch(() => null);
}

function relayError(
  status: number,
  body: unknown,
  fallback: string,
  retryAfter?: string | null,
) {
  const headers = retryAfter ? { "Retry-After": retryAfter } : undefined;
  if (typeof body === "object" && body !== null) {
    return NextResponse.json(body, { status, headers });
  }

  return NextResponse.json(
    { success: false, code: "OPERATOR_SESSION_ERROR", message: fallback },
    { status, headers },
  );
}

export async function GET() {
  const status = await getOperatorSecurityStatus();
  if (!status) {
    return NextResponse.json(
      {
        success: false,
        code: "BACKEND_UNAVAILABLE",
        message: "백엔드 운영자 권한 상태를 확인할 수 없습니다.",
      },
      { status: 503 },
    );
  }

  return NextResponse.json({ ...status, authMode: getOperatorAuthMode() });
}

export async function POST(request: NextRequest) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json(
      {
        success: false,
        code: "CROSS_ORIGIN_OPERATOR_LOGIN_DENIED",
        message: "다른 출처에서 운영자 로그인을 요청할 수 없습니다.",
      },
      { status: 403 },
    );
  }

  if (getOperatorAuthMode() !== "session") {
    return NextResponse.json(
      {
        success: false,
        code: "OPERATOR_SESSION_MODE_DISABLED",
        message:
          "브라우저 로그인을 사용하려면 VISIONFLOW_WEB_AUTH_MODE=session을 설정하세요.",
      },
      { status: 409 },
    );
  }

  const body: unknown = await request.json().catch(() => null);
  const username =
    typeof body === "object" &&
    body !== null &&
    "username" in body &&
    typeof body.username === "string"
      ? body.username.trim()
      : "";
  const password =
    typeof body === "object" &&
    body !== null &&
    "password" in body &&
    typeof body.password === "string"
      ? body.password
      : "";
  const operatorKey =
    typeof body === "object" &&
    body !== null &&
    "operatorKey" in body &&
    typeof body.operatorKey === "string"
      ? body.operatorKey.trim()
      : "";

  const passwordLogin = username.length > 0 || password.length > 0;
  if (
    passwordLogin &&
    (username.length === 0 ||
      username.length > 100 ||
      password.length === 0 ||
      password.length > 4096)
  ) {
    return NextResponse.json(
      {
        success: false,
        code: "INVALID_OPERATOR_LOGIN_REQUEST",
        message: "사용자 ID와 비밀번호를 확인하세요.",
      },
      { status: 400 },
    );
  }

  if (
    !passwordLogin &&
    (operatorKey.length < 24 || operatorKey.length > 4096)
  ) {
    return NextResponse.json(
      {
        success: false,
        code: "INVALID_OPERATOR_LOGIN_REQUEST",
        message: "올바른 운영자 인증 키를 입력하세요.",
      },
      { status: 400 },
    );
  }

  const backendHeaders = new Headers({
    Accept: "application/json",
  });
  let backendRequestBody: string | undefined;
  if (passwordLogin) {
    backendHeaders.set("Content-Type", "application/json");
    backendRequestBody = JSON.stringify({ username, password });
  } else {
    backendHeaders.set(OPERATOR_KEY_HEADER, operatorKey);
  }

  try {
    const backendResponse = await fetch(
      `${BACKEND_API_URL}/api/security/sessions`,
      {
        method: "POST",
        headers: backendHeaders,
        body: backendRequestBody,
        cache: "no-store",
        signal: AbortSignal.timeout(5_000),
      },
    );
    const backendBody = await readBody(backendResponse);

    if (!backendResponse.ok) {
      return relayError(
        backendResponse.status,
        backendBody,
        "운영자 로그인에 실패했습니다.",
        backendResponse.headers.get("retry-after"),
      );
    }
    if (!isBackendOperatorSession(backendBody)) {
      return NextResponse.json(
        {
          success: false,
          code: "INVALID_OPERATOR_SESSION_RESPONSE",
          message: "백엔드 로그인 응답 형식이 올바르지 않습니다.",
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
        message: "백엔드 운영자 로그인 서비스에 연결할 수 없습니다.",
      },
      { status: 503 },
    );
  }
}

export async function DELETE(request: NextRequest) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json(
      {
        success: false,
        code: "CROSS_ORIGIN_OPERATOR_LOGOUT_DENIED",
        message: "다른 출처에서 운영자 로그아웃을 요청할 수 없습니다.",
      },
      { status: 403 },
    );
  }

  const cookieStore = await cookies();
  const token = cookieStore.get(OPERATOR_SESSION_COOKIE)?.value.trim();

  if (token) {
    await fetch(`${BACKEND_API_URL}/api/security/sessions/current`, {
      method: "DELETE",
      headers: {
        Accept: "application/json",
        [OPERATOR_SESSION_HEADER]: token,
      },
      cache: "no-store",
      signal: AbortSignal.timeout(5_000),
    }).catch(() => null);
  }

  const response = new NextResponse(null, { status: 204 });
  response.cookies.set({
    name: OPERATOR_SESSION_COOKIE,
    value: "",
    httpOnly: true,
    sameSite: "lax",
    secure:
      process.env.VISIONFLOW_WEB_SECURE_COOKIES?.trim().toLowerCase() ===
      "true",
    path: "/",
    maxAge: 0,
  });
  return response;
}
