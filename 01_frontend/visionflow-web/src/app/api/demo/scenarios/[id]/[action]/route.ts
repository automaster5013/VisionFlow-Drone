import { type NextRequest } from "next/server";

import {
    badDemoRequest,
    isScenarioId,
    proxyDemoScenarioRequest,
} from "@/lib/server/demo-scenario-proxy";
import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";

interface RouteContext {
    params: Promise<{ id: string; action: string }>;
}

const ACTIONS = new Set(["detect", "escalate", "resolve", "complete"]);

export async function POST(request: NextRequest, context: RouteContext) {
    const rejected = rejectCrossOriginOperatorMutation(request);
    if (rejected) {
        return rejected;
    }

    const { id, action } = await context.params;
    if (!isScenarioId(id)) {
        return badDemoRequest("잘못된 시연 시나리오 ID입니다.");
    }
    if (!ACTIONS.has(action)) {
        return badDemoRequest("지원하지 않는 시연 동작입니다.");
    }

    return proxyDemoScenarioRequest(
        `/api/demo/scenarios/${encodeURIComponent(id)}/${action}`,
        { method: "POST", headers: { Accept: "application/json" } },
        `시연 시나리오 ${action}`,
    );
}
