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

export async function PATCH(
    request: NextRequest,
    context: RouteContext,
): Promise<NextResponse> {
    const rejected = rejectCrossOriginOperatorMutation(request);
    if (rejected) {
        return rejected;
    }

    const apiBaseUrl = getApiBaseUrl();
    const { id } = await context.params;
    if (!/^\d+$/.test(id) || !Number.isSafeInteger(Number(id)) || Number(id) < 1) {
        return NextResponse.json(
            { success: false, code: "INVALID_DRONE_ID", message: "잘못된 드론 ID입니다." },
            { status: 400, headers: { "Cache-Control": "no-store" } },
        );
    }
    const parsedBody = await readBoundedMutationJson(request, 8 * 1024, "드론 상태 변경");
    if (!parsedBody.ok) return parsedBody.response;

    try {
        const response = await fetch(
            `${apiBaseUrl}/api/drones/${id}/status`,
            await withBackendOperatorAuth({
                method: "PATCH",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(parsedBody.body),
                cache: "no-store",
            }),
        );

        const parsed = await readBoundedJsonResponse(response, 64 * 1024);
        if (!parsed.ok) {
            return NextResponse.json(
                { success: false, code: "INVALID_BACKEND_RESPONSE", message: "백엔드 상태 응답이 유효하지 않거나 허용 크기를 초과했습니다.", errors: {}, timestamp: new Date().toISOString() },
                { status: 502, headers: { "Cache-Control": "no-store" } },
            );
        }

        return NextResponse.json(parsed.value, {
            status: response.status,
            headers: { "Cache-Control": "no-store" },
        });
    } catch (error) {
        console.error("Drone status PATCH proxy error:", error);

        return NextResponse.json(
            {
                success: false,
                code: "BACKEND_CONNECTION_ERROR",
                message: "드론 상태 변경 요청을 처리할 수 없습니다.",
                errors: {},
                timestamp: new Date().toISOString(),
            },
            {
                status: 503,
            },
        );
    }
}
