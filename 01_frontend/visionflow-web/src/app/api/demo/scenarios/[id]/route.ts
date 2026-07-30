import { type NextRequest } from "next/server";

import {
    badDemoRequest,
    isScenarioId,
    proxyDemoScenarioRequest,
} from "@/lib/server/demo-scenario-proxy";

interface RouteContext {
    params: Promise<{ id: string }>;
}

export async function GET(_request: NextRequest, context: RouteContext) {
    const { id } = await context.params;
    if (!isScenarioId(id)) {
        return badDemoRequest("잘못된 시연 시나리오 ID입니다.");
    }

    return proxyDemoScenarioRequest(
        `/api/demo/scenarios/${encodeURIComponent(id)}`,
        { method: "GET", headers: { Accept: "application/json" } },
        "시연 시나리오 조회",
    );
}
