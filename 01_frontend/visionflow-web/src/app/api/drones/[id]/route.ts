import { NextRequest, NextResponse } from "next/server";

import { withBackendOperatorAuth } from "@/lib/server/operator-auth";
import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";

const DEFAULT_API_URL = "http://localhost:8080";

interface RouteContext {
    params: Promise<{
        id: string;
    }>;
}

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
    _request: NextRequest,
    context: RouteContext,
): Promise<NextResponse> {
    const apiBaseUrl = getApiBaseUrl();
    const { id } = await context.params;

    try {
        const response = await fetch(
            `${apiBaseUrl}/api/drones/${id}`,
            {
                method: "GET",
                headers: {
                    Accept: "application/json",
                },
                cache: "no-store",
            },
        );

        return proxyResponse(response);
    } catch (error) {
        console.error("Drone detail proxy error:", error);

        return NextResponse.json(
            {
                success: false,
                code: "BACKEND_CONNECTION_ERROR",
                message: "드론 정보를 조회할 수 없습니다.",
                errors: {},
                timestamp: new Date().toISOString(),
            },
            {
                status: 503,
            },
        );
    }
}

export async function PUT(
    request: NextRequest,
    context: RouteContext,
): Promise<NextResponse> {
    const rejected = rejectCrossOriginOperatorMutation(request);
    if (rejected) {
        return rejected;
    }

    const apiBaseUrl = getApiBaseUrl();
    const { id } = await context.params;

    try {
        const requestBody: unknown = await request.json();

        const response = await fetch(
            `${apiBaseUrl}/api/drones/${id}`,
            await withBackendOperatorAuth({
                method: "PUT",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(requestBody),
                cache: "no-store",
            }),
        );

        return proxyResponse(response);
    } catch (error) {
        console.error("Drone PUT proxy error:", error);

        return NextResponse.json(
            {
                success: false,
                code: "BACKEND_CONNECTION_ERROR",
                message: "드론 수정 요청을 처리할 수 없습니다.",
                errors: {},
                timestamp: new Date().toISOString(),
            },
            {
                status: 503,
            },
        );
    }
}

export async function DELETE(
    request: NextRequest,
    context: RouteContext,
): Promise<NextResponse> {
    const rejected = rejectCrossOriginOperatorMutation(request);
    if (rejected) {
        return rejected;
    }

    const apiBaseUrl = getApiBaseUrl();
    const { id } = await context.params;

    try {
        const response = await fetch(
            `${apiBaseUrl}/api/drones/${id}`,
            await withBackendOperatorAuth({
                method: "DELETE",
                headers: {
                    Accept: "application/json",
                },
                cache: "no-store",
            }),
        );

        return proxyResponse(response);
    } catch (error) {
        console.error("Drone DELETE proxy error:", error);

        return NextResponse.json(
            {
                success: false,
                code: "BACKEND_CONNECTION_ERROR",
                message: "드론 삭제 요청을 처리할 수 없습니다.",
                errors: {},
                timestamp: new Date().toISOString(),
            },
            {
                status: 503,
            },
        );
    }
}
