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

    try {
        const requestBody: unknown = await request.json();

        const response = await fetch(
            `${apiBaseUrl}/api/drones/${id}/status`,
            await withBackendOperatorAuth({
                method: "PATCH",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(requestBody),
                cache: "no-store",
            }),
        );

        const body: unknown = await response.json();

        return NextResponse.json(body, {
            status: response.status,
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
