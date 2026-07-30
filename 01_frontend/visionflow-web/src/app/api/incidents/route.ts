import { type NextRequest } from "next/server";

import {
    badIncidentRequest,
    proxyIncidentRequest,
} from "@/lib/server/incident-proxy";

const SOURCE_TYPES = new Set([
    "AI_ALERT",
    "GEOFENCE",
    "FLIGHT_QUALITY",
    "FLIGHT_GATE",
]);
const PRIORITIES = new Set(["LOW", "MEDIUM", "HIGH", "CRITICAL"]);
const STATUSES = new Set(["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"]);

export async function GET(request: NextRequest) {
    const input = request.nextUrl.searchParams;
    const rawLimit = input.get("limit") ?? "100";

    if (!/^\d+$/.test(rawLimit)) {
        return badIncidentRequest("Incident 조회 개수는 숫자여야 합니다.");
    }

    const limit = Number(rawLimit);
    if (!Number.isInteger(limit) || limit < 1 || limit > 500) {
        return badIncidentRequest("Incident 조회 개수는 1~500이어야 합니다.");
    }

    const droneId = input.get("droneId")?.trim() ?? "";
    if (droneId && (!/^\d+$/.test(droneId) || Number(droneId) < 1)) {
        return badIncidentRequest("드론 ID는 1 이상의 정수여야 합니다.");
    }

    const sourceType = input.get("sourceType")?.trim().toUpperCase() ?? "";
    if (sourceType && !SOURCE_TYPES.has(sourceType)) {
        return badIncidentRequest("지원하지 않는 Incident 원본 유형입니다.");
    }

    const priority = input.get("priority")?.trim().toUpperCase() ?? "";
    if (priority && !PRIORITIES.has(priority)) {
        return badIncidentRequest("지원하지 않는 Incident 우선순위입니다.");
    }

    const status = input.get("status")?.trim().toUpperCase() ?? "";
    if (status && !STATUSES.has(status)) {
        return badIncidentRequest("지원하지 않는 Incident 상태입니다.");
    }

    const assignee = input.get("assignee")?.trim() ?? "";
    if (assignee.length > 100) {
        return badIncidentRequest("Incident 담당자는 100자 이하여야 합니다.");
    }

    const from = input.get("from")?.trim() ?? "";
    const to = input.get("to")?.trim() ?? "";
    if (from && !Number.isFinite(Date.parse(from))) {
        return badIncidentRequest("Incident 조회 시작 시각이 올바르지 않습니다.");
    }
    if (to && !Number.isFinite(Date.parse(to))) {
        return badIncidentRequest("Incident 조회 종료 시각이 올바르지 않습니다.");
    }
    if (from && to && Date.parse(from) > Date.parse(to)) {
        return badIncidentRequest(
            "Incident 조회 시작 시각은 종료 시각보다 늦을 수 없습니다.",
        );
    }

    const output = new URLSearchParams({ limit: String(limit) });
    if (droneId) output.set("droneId", droneId);
    if (sourceType) output.set("sourceType", sourceType);
    if (priority) output.set("priority", priority);
    if (status) output.set("status", status);
    if (assignee) output.set("assignee", assignee);
    if (from) output.set("from", from);
    if (to) output.set("to", to);

    return proxyIncidentRequest(
        `/api/incidents?${output.toString()}`,
        { method: "GET", headers: { Accept: "application/json" } },
        "Incident 목록",
    );
}
