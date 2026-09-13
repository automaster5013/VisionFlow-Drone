import { type NextRequest, NextResponse } from "next/server";

import {
    isPositiveIntegerPath,
    proxyAiAlertRequest,
} from "@/lib/server/ai-alert-proxy";
import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";
import { readBoundedMutationText } from "@/lib/server/bounded-request-body";

interface RouteContext {
    params: Promise<{
        id: string;
    }>;
}

export async function PATCH(request: NextRequest, context: RouteContext) {
    const rejected = rejectCrossOriginOperatorMutation(request);
    if (rejected) {
        return rejected;
    }

    const { id } = await context.params;

    if (!isPositiveIntegerPath(id)) {
        return NextResponse.json(
            { message: "잘못된 AI 경보 ID입니다." },
            { status: 400, headers: { "Cache-Control": "no-store" } },
        );
    }

    const parsedBody = await readBoundedMutationText(request, 16 * 1024, "AI 경보 해결 처리");
    if (!parsedBody.ok) return parsedBody.response;

    return proxyAiAlertRequest(
        `/api/ai/alerts/${encodeURIComponent(id)}/resolve`,
        {
            method: "PATCH",
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
            },
            body: parsedBody.body,
        },
        "AI 경보 해결 처리",
    );
}
