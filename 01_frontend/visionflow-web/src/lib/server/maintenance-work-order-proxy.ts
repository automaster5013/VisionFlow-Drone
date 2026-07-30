import "server-only";

import { NextResponse } from "next/server";

import { withBackendOperatorAuth } from "@/lib/server/operator-auth";

const BACKEND_API_URL = (
  process.env.SPRING_API_URL ??
  process.env.BACKEND_API_URL ??
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8080"
).replace(/\/$/, "");

export function badMaintenanceRequest(message: string) {
  return NextResponse.json(
    { message },
    { status: 400, headers: { "Cache-Control": "no-store" } },
  );
}

export function isPositiveMaintenanceId(value: string): boolean {
  return /^\d+$/.test(value) && Number(value) >= 1;
}

export async function proxyMaintenanceRequest(
  backendPath: string,
  init: RequestInit,
  label: string,
) {
  try {
    const response = await fetch(
      `${BACKEND_API_URL}${backendPath}`,
      await withBackendOperatorAuth({
        ...init,
        cache: "no-store",
        signal: AbortSignal.timeout(15_000),
      }),
    );
    const body = await response.text();

    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    console.error(`${label} 프록시 오류:`, error);

    return NextResponse.json(
      { message: "백엔드 점검 작업지시 API에 연결할 수 없습니다." },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
