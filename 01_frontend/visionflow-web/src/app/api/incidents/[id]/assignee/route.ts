import { type NextRequest } from "next/server";

import {
    badIncidentRequest,
    isPositiveIntegerPath,
    proxyIncidentRequest,
} from "@/lib/server/incident-proxy";
import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";

interface RouteContext {
    params: Promise<{ id: string }>;
}

export async function PATCH(request: NextRequest, context: RouteContext) {
    const rejected = rejectCrossOriginOperatorMutation(request);
    if (rejected) {
        return rejected;
    }

    const { id } = await context.params;
    if (!isPositiveIntegerPath(id)) {
        return badIncidentRequest("잘못된 Incident ID입니다.");
    }

    return proxyIncidentRequest(
        `/api/incidents/${encodeURIComponent(id)}/assignee`,
        {
            method: "PATCH",
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
            },
            body: await request.text(),
        },
        "Incident 담당자 지정",
    );
}
