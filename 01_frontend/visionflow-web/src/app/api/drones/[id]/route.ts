import { NextRequest, NextResponse } from "next/server";

import { withBackendOperatorAuth } from "@/lib/server/operator-auth";
import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";
import { readBoundedMutationJson } from "@/lib/server/bounded-request-body";
import { readBoundedJsonResponse } from "@/lib/request-body-limit";

const DEFAULT_API_URL = "http://localhost:8080";

interface RouteContext {
    params: Promise<{
        id: string;
    }>;
}

function getApiBaseUrl(): string {
    return process.env.SPRING_API_URL ?? DEFAULT_API_URL;
}

function isValidDroneId(value: string): boolean {
    return /^\d+$/.test(value) && Number.isSafeInteger(Number(value)) && Number(value) > 0;
}

async function proxyResponse(
    response: Response,
): Promise<NextResponse> {
    const contentType =
        response.headers.get("content-type") ?? "";

    if (contentType.includes("application/json")) {
        const parsed = await readBoundedJsonResponse(response, 4 * 1024 * 1024);
        if (!parsed.ok) {
            return NextResponse.json(
                { success: false, code: "INVALID_BACKEND_RESPONSE", message: "백엔드 응답이 유효하지 않거나 허용 크기를 초과했습니다.", errors: {}, timestamp: new Date().toISOString() },
                { status: 502, headers: { "Cache-Control": "no-store" } },
            );
        }

        return NextResponse.json(parsed.value, {
            status: response.status,
            headers: { "Cache-Control": "no-store" },
        });
    }
    await response.body?.cancel();

    return NextResponse.json(
        {
            success: false,
            code: "INVALID_BACKEND_RESPONSE",
            message: "백엔드 응답 형식이 올바르지 않습니다.",
            errors: {},
            timestamp: new Date().toISOString(),
        },
        {
            status: response.status,
            headers: { "Cache-Control": "no-store" },
        },
    );
}

export async function GET(
    _request: NextRequest,
    context: RouteContext,
): Promise<NextResponse> {
    const apiBaseUrl = getApiBaseUrl();
    const { id } = await context.params;
    if (!isValidDroneId(id)) {
        return NextResponse.json(
            { success: false, code: "INVALID_DRONE_ID", message: "잘못된 드론 ID입니다." },
            { status: 400, headers: { "Cache-Control": "no-store" } },
        );
    }

    try {
        const response = await fetch(
            `${apiBaseUrl}/api/drones/${id}`,
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
    if (!isValidDroneId(id)) {
        return NextResponse.json(
            { success: false, code: "INVALID_DRONE_ID", message: "잘못된 드론 ID입니다." },
            { status: 400, headers: { "Cache-Control": "no-store" } },
        );
    }
    const parsedBody = await readBoundedMutationJson(request, 16 * 1024, "드론 수정");
    if (!parsedBody.ok) return parsedBody.response;

    try {
        const response = await fetch(
            `${apiBaseUrl}/api/drones/${id}`,
            await withBackendOperatorAuth({
                method: "PUT",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(parsedBody.body),
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
    if (!isValidDroneId(id)) {
        return NextResponse.json(
            { success: false, code: "INVALID_DRONE_ID", message: "잘못된 드론 ID입니다." },
            { status: 400, headers: { "Cache-Control": "no-store" } },
        );
    }

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
