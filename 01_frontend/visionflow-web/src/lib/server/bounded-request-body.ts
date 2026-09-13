import { type NextRequest, NextResponse } from "next/server";

import {
  readBoundedJsonRequest,
  readBoundedTextRequest,
} from "@/lib/request-body-limit";

export async function readBoundedMutationJson(
  request: NextRequest,
  maxBytes: number,
  message: string,
): Promise<
  | { ok: true; body: unknown }
  | { ok: false; response: NextResponse }
> {
  const result = await readBoundedJsonRequest(request, maxBytes);
  if (result.ok) {
    return { ok: true, body: result.value };
  }

  return {
    ok: false,
    response: NextResponse.json(
      {
        success: false,
        code:
          result.reason === "too_large"
            ? "REQUEST_BODY_TOO_LARGE"
            : "INVALID_REQUEST_BODY",
        message:
          result.reason === "too_large"
            ? `${message} 요청이 허용 크기를 초과했습니다.`
            : `${message} 요청 본문 형식이 올바르지 않습니다.`,
      },
      {
        status: result.reason === "too_large" ? 413 : 400,
        headers: { "Cache-Control": "no-store" },
      },
    ),
  };
}

export async function readBoundedMutationText(
  request: NextRequest,
  maxBytes: number,
  message: string,
): Promise<{ ok: true; body: string } | { ok: false; response: NextResponse }> {
  const result = await readBoundedTextRequest(request, maxBytes);
  if (result.ok) {
    return { ok: true, body: result.value };
  }

  return {
    ok: false,
    response: NextResponse.json(
      {
        success: false,
        code:
          result.reason === "too_large"
            ? "REQUEST_BODY_TOO_LARGE"
            : "INVALID_REQUEST_BODY",
        message:
          result.reason === "too_large"
            ? `${message} 요청이 허용 크기를 초과했습니다.`
            : `${message} 요청 본문을 읽을 수 없습니다.`,
      },
      {
        status: result.reason === "too_large" ? 413 : 400,
        headers: { "Cache-Control": "no-store" },
      },
    ),
  };
}
