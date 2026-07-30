import "server-only";

import {
    parseIncidentList,
    type IncidentItem,
    type IncidentQuery,
} from "@/types/incident";

const DEFAULT_API_URL = "http://localhost:8080";

function getApiBaseUrl(): string {
    return (
        process.env.SPRING_API_URL ??
        process.env.BACKEND_API_URL ??
        process.env.API_BASE_URL ??
        DEFAULT_API_URL
    ).replace(/\/$/, "");
}

function buildSearchParams(query: IncidentQuery): URLSearchParams {
    const limit = query.limit ?? 100;

    if (!Number.isInteger(limit) || limit < 1 || limit > 500) {
        throw new Error("Incident 조회 개수는 1~500이어야 합니다.");
    }

    if (
        query.droneId !== undefined &&
        (!Number.isInteger(query.droneId) || query.droneId < 1)
    ) {
        throw new Error("Incident 조회 드론 ID가 올바르지 않습니다.");
    }

    if (query.assignee && query.assignee.trim().length > 100) {
        throw new Error("Incident 담당자는 100자 이하여야 합니다.");
    }

    if (query.from && !Number.isFinite(Date.parse(query.from))) {
        throw new Error("Incident 조회 시작 시각이 올바르지 않습니다.");
    }

    if (query.to && !Number.isFinite(Date.parse(query.to))) {
        throw new Error("Incident 조회 종료 시각이 올바르지 않습니다.");
    }

    if (
        query.from &&
        query.to &&
        Date.parse(query.from) > Date.parse(query.to)
    ) {
        throw new Error("Incident 조회 시작 시각은 종료 시각보다 늦을 수 없습니다.");
    }

    const searchParams = new URLSearchParams({ limit: String(limit) });

    if (query.droneId !== undefined) {
        searchParams.set("droneId", String(query.droneId));
    }
    if (query.sourceType) {
        searchParams.set("sourceType", query.sourceType);
    }
    if (query.priority) {
        searchParams.set("priority", query.priority);
    }
    if (query.status) {
        searchParams.set("status", query.status);
    }
    if (query.assignee?.trim()) {
        searchParams.set("assignee", query.assignee.trim());
    }
    if (query.from) {
        searchParams.set("from", query.from);
    }
    if (query.to) {
        searchParams.set("to", query.to);
    }

    return searchParams;
}

async function readFailureMessage(response: Response): Promise<string> {
    try {
        const body: unknown = await response.json();

        if (
            typeof body === "object" &&
            body !== null &&
            "message" in body &&
            typeof body.message === "string"
        ) {
            return body.message;
        }
    } catch {
        // JSON 오류 본문이 아니면 HTTP 상태를 사용합니다.
    }

    return `HTTP ${response.status} ${response.statusText}`;
}

export async function getIncidents(
    query: IncidentQuery = {},
): Promise<IncidentItem[]> {
    const searchParams = buildSearchParams(query);
    const apiBaseUrl = getApiBaseUrl();
    let response: Response;

    try {
        response = await fetch(
            `${apiBaseUrl}/api/incidents?${searchParams.toString()}`,
            {
                method: "GET",
                headers: { Accept: "application/json" },
                cache: "no-store",
                signal: AbortSignal.timeout(5_000),
            },
        );
    } catch (error) {
        const message =
            error instanceof Error ? error.message : "Unknown connection error";

        throw new Error(`Incident API 연결에 실패했습니다: ${message}`);
    }

    if (!response.ok) {
        throw new Error(
            `Incident API 호출 실패: ${await readFailureMessage(response)}`,
        );
    }

    let body: unknown;

    try {
        body = await response.json();
    } catch {
        throw new Error("Incident API 응답을 JSON으로 변환할 수 없습니다.");
    }

    const incidents = parseIncidentList(body);

    if (!incidents) {
        throw new Error("Incident API 응답 형식이 올바르지 않습니다.");
    }

    return incidents;
}
