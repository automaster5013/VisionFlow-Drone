import { type NextRequest, NextResponse } from "next/server";

import {
    isPositiveIntegerPath,
    proxyAiAlertRequest,
} from "@/lib/server/ai-alert-proxy";
import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";

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

    return proxyAiAlertRequest(
        `/api/ai/alerts/${encodeURIComponent(id)}/acknowledge`,
        {
            method: "PATCH",
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
            },
            body: await request.text(),
        },
        "AI 경보 확인 처리",
    );
}
