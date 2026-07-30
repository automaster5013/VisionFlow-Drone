import { type NextRequest, NextResponse } from "next/server";

import {
    isPositiveIntegerPath,
    proxyAiAlertRequest,
} from "@/lib/server/ai-alert-proxy";

interface RouteContext {
    params: Promise<{
        id: string;
    }>;
}

export async function GET(_request: NextRequest, context: RouteContext) {
    const { id } = await context.params;

    if (!isPositiveIntegerPath(id)) {
        return NextResponse.json(
            { message: "잘못된 AI 경보 ID입니다." },
            { status: 400, headers: { "Cache-Control": "no-store" } },
        );
    }

    return proxyAiAlertRequest(
        `/api/ai/alerts/${encodeURIComponent(id)}`,
        {
            method: "GET",
            headers: { Accept: "application/json" },
        },
        "AI 경보 상세",
    );
}
