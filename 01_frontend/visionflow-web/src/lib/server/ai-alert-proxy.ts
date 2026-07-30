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

export function isPositiveIntegerPath(value: string): boolean {
    return /^\d+$/.test(value) && Number(value) >= 1;
}

export async function proxyAiAlertRequest(
    backendPath: string,
    init: RequestInit,
    logLabel: string,
) {
    try {
        const response = await fetch(`${BACKEND_API_URL}${backendPath}`, await withBackendOperatorAuth({
            ...init,
            cache: "no-store",
            signal: AbortSignal.timeout(10_000),
        }));
        const responseBody = await response.text();

        return new NextResponse(responseBody, {
            status: response.status,
            headers: {
                "Content-Type":
                    response.headers.get("content-type") ?? "application/json",
                "Cache-Control": "no-store",
            },
        });
    } catch (error) {
        console.error(`${logLabel} 프록시 오류:`, error);

        return NextResponse.json(
            { message: "백엔드 AI 경보 API에 연결할 수 없습니다." },
            { status: 502, headers: { "Cache-Control": "no-store" } },
        );
    }
}
