import "server-only";

import { type NextRequest, NextResponse } from "next/server";

import {
  OPERATOR_SESSION_COOKIE,
  withBackendOperatorAuth,
} from "@/lib/server/operator-auth";
import { readBoundedRequestBody } from "@/lib/request-body-limit";

const BACKEND_API_URL = (
  process.env.SPRING_API_URL ??
  process.env.BACKEND_API_URL ??
  process.env.API_BASE_URL ??
  "http://localhost:8080"
).replace(/\/$/, "");

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MAX_PAIRING_REQUEST_BYTES = 8 * 1024;
const MAX_PAIRING_RESPONSE_BYTES = 16 * 1024;

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
    let body = "";
    if (method === "POST") {
      const contentLength = request.headers.get("content-length");
      if (
        contentLength !== null &&
        (!/^\d+$/.test(contentLength) || !Number.isSafeInteger(Number(contentLength)))
      ) {
        return NextResponse.json(
          {
            success: false,
            code: "INVALID_CONTENT_LENGTH",
            message: "Content-Length 헤더 형식이 올바르지 않습니다.",
          },
          { status: 400, headers: { "Cache-Control": "no-store" } },
        );
      }
      if (Number(contentLength) > MAX_PAIRING_REQUEST_BYTES) {
        return NextResponse.json(
          {
            success: false,
            code: "OPERATOR_PAIRING_REQUEST_TOO_LARGE",
            message: "QR 페어링 요청이 허용 크기를 초과했습니다.",
          },
          { status: 413, headers: { "Cache-Control": "no-store" } },
        );
      }

      let boundedBody: ArrayBuffer | null;
      try {
        boundedBody = await readBoundedRequestBody(
          request.body,
          MAX_PAIRING_REQUEST_BYTES,
        );
      } catch {
        return NextResponse.json(
          {
            success: false,
            code: "INVALID_OPERATOR_PAIRING_REQUEST",
            message: "QR 페어링 요청 본문을 읽을 수 없습니다.",
          },
          { status: 400, headers: { "Cache-Control": "no-store" } },
        );
      }
      if (boundedBody === null) {
        return NextResponse.json(
          {
            success: false,
            code: "OPERATOR_PAIRING_REQUEST_TOO_LARGE",
            message: "QR 페어링 요청이 허용 크기를 초과했습니다.",
          },
          { status: 413, headers: { "Cache-Control": "no-store" } },
        );
      }
      try {
        body = new TextDecoder("utf-8", { fatal: true }).decode(boundedBody);
      } catch {
        return NextResponse.json(
          {
            success: false,
            code: "INVALID_OPERATOR_PAIRING_REQUEST",
            message: "QR 페어링 요청의 문자 인코딩이 올바르지 않습니다.",
          },
          { status: 400, headers: { "Cache-Control": "no-store" } },
        );
      }
    }
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
    const boundedResponse = await readBoundedRequestBody(
      response.body,
      MAX_PAIRING_RESPONSE_BYTES,
    );
    if (boundedResponse === null) {
      return NextResponse.json(
        {
          success: false,
          code: "OPERATOR_PAIRING_RESPONSE_TOO_LARGE",
          message: "QR 페어링 서비스 응답 크기가 허용 범위를 초과했습니다.",
        },
        { status: 502, headers: { "Cache-Control": "no-store" } },
      );
    }
    const responseText = new TextDecoder("utf-8").decode(boundedResponse);

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
