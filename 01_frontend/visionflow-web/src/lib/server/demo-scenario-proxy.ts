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

export function badDemoRequest(message: string) {
    return NextResponse.json(
        { message },
        { status: 400, headers: { "Cache-Control": "no-store" } },
    );
}

export function isScenarioId(value: string): boolean {
    return /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
        value,
    );
}

export async function proxyDemoScenarioRequest(
    backendPath: string,
    init: RequestInit,
    logLabel: string,
) {
    try {
        const response = await fetch(`${BACKEND_API_URL}${backendPath}`, await withBackendOperatorAuth({
            ...init,
            cache: "no-store",
            signal: AbortSignal.timeout(15_000),
        }));
        const responseBody = await response.text();

        return new NextResponse(responseBody, {
            status: response.status,
            headers: {
                "Content-Type":
                    response.headers.get("content-type") ??
                    "application/json",
                "Cache-Control": "no-store",
            },
        });
    } catch (error) {
        console.error(`${logLabel} 프록시 오류:`, error);

        return NextResponse.json(
            {
                message:
                    "백엔드 시연 API에 연결할 수 없습니다. Spring 서버와 visionflow.demo.enabled 설정을 확인해 주세요.",
            },
            { status: 502, headers: { "Cache-Control": "no-store" } },
        );
    }
}
