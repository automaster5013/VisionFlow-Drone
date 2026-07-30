import { type NextRequest } from "next/server";

import {
    badIncidentRequest,
    isPositiveIntegerPath,
    proxyIncidentRequest,
} from "@/lib/server/incident-proxy";

interface RouteContext {
    params: Promise<{ id: string }>;
}

export async function GET(_request: NextRequest, context: RouteContext) {
    const { id } = await context.params;

    if (!isPositiveIntegerPath(id)) {
        return badIncidentRequest("잘못된 Incident ID입니다.");
    }

    return proxyIncidentRequest(
        `/api/incidents/${encodeURIComponent(id)}/report`,
        { method: "GET", headers: { Accept: "application/json" } },
        "Incident 보고서",
    );
}
