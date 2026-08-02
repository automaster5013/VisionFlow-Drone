import { NextRequest, NextResponse } from "next/server";

import { withBackendOperatorAuth } from "@/lib/server/operator-auth";
import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";

const DEFAULT_API_URL = "http://localhost:8080";

function getApiBaseUrl(): string {
    return process.env.SPRING_API_URL ?? DEFAULT_API_URL;
}

async function proxyResponse(
    response: Response,
): Promise<NextResponse> {
    const contentType =
        response.headers.get("content-type") ?? "";

    if (contentType.includes("application/json")) {
        const body: unknown = await response.json();

        return NextResponse.json(body, {
            status: response.status,
        });
    }

    const text = await response.text();

    return NextResponse.json(
        {
            success: false,
            code: "INVALID_BACKEND_RESPONSE",
            message: text || "백엔드 응답 형식이 올바르지 않습니다.",
            errors: {},
            timestamp: new Date().toISOString(),
        },
        {
            status: response.status,
        },
    );
}

export async function GET(
    request: NextRequest,
): Promise<NextResponse> {
    const apiBaseUrl = getApiBaseUrl();
    const status = request.nextUrl.searchParams.get("status");

    const query = status
        ? `?status=${encodeURIComponent(status)}`
        : "";

    try {
        const response = await fetch(
            `${apiBaseUrl}/api/drones${query}`,
            await withBackendOperatorAuth({
                method: "GET",
                headers: {
                    Accept: "application/json",
                },
                cache: "no-store",
            }),
        );

        return proxyResponse(response);
    } catch (error) {
        console.error("Drone GET proxy error:", error);

        return NextResponse.json(
            {
                success: false,
                code: "BACKEND_CONNECTION_ERROR",
                message: "Spring Boot 서버에 연결할 수 없습니다.",
                errors: {},
                timestamp: new Date().toISOString(),
            },
            {
                status: 503,
            },
        );
    }
}

export async function POST(
    request: NextRequest,
): Promise<NextResponse> {
    const rejected = rejectCrossOriginOperatorMutation(request);
    if (rejected) {
        return rejected;
    }

    const apiBaseUrl = getApiBaseUrl();

    try {
        const requestBody: unknown = await request.json();

        const response = await fetch(`${apiBaseUrl}/api/drones`, await withBackendOperatorAuth({
            method: "POST",
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
            },
            body: JSON.stringify(requestBody),
            cache: "no-store",
        }));

        return proxyResponse(response);
    } catch (error) {
        console.error("Drone POST proxy error:", error);

        return NextResponse.json(
            {
                success: false,
                code: "BACKEND_CONNECTION_ERROR",
                message: "드론 등록 요청을 처리할 수 없습니다.",
                errors: {},
                timestamp: new Date().toISOString(),
            },
            {
                status: 503,
            },
        );
    }
}
