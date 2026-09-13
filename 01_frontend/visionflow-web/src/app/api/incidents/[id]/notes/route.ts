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

export async function POST(request: NextRequest, context: RouteContext) {
    const rejected = rejectCrossOriginOperatorMutation(request);
    if (rejected) {
        return rejected;
    }

    const { id } = await context.params;
    if (!isPositiveIntegerPath(id)) {
        return badIncidentRequest("잘못된 Incident ID입니다.");
    }

    const parsedBody = await readBoundedMutationText(request, 64 * 1024, "Incident 조치 메모");
    if (!parsedBody.ok) return parsedBody.response;

    return proxyIncidentRequest(
        `/api/incidents/${encodeURIComponent(id)}/notes`,
        {
            method: "POST",
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
            },
            body: parsedBody.body,
        },
        "Incident 조치 메모",
    );
}
