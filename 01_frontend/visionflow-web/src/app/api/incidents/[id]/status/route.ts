import { type NextRequest } from "next/server";

import {
    badIncidentRequest,
    isPositiveIntegerPath,
    proxyIncidentRequest,
} from "@/lib/server/incident-proxy";
import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";
import { readBoundedMutationText } from "@/lib/server/bounded-request-body";

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

    const parsedBody = await readBoundedMutationText(request, 16 * 1024, "Incident 상태 변경");
    if (!parsedBody.ok) return parsedBody.response;

    return proxyIncidentRequest(
        `/api/incidents/${encodeURIComponent(id)}/status`,
        {
            method: "PATCH",
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
            },
            body: parsedBody.body,
        },
        "Incident 상태 변경",
    );
}
