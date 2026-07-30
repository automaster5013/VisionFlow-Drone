import "server-only";

import {
    parseAiAlertList,
    type AiAlertItem,
    type AiAlertQuery,
} from "@/types/ai-alert";

const DEFAULT_API_URL = "http://localhost:8080";

function getApiBaseUrl(): string {
    return (
        process.env.SPRING_API_URL ??
        process.env.BACKEND_API_URL ??
        process.env.API_BASE_URL ??
        DEFAULT_API_URL
    ).replace(/\/$/, "");
}

function buildSearchParams(query: AiAlertQuery): URLSearchParams {
    const limit = query.limit ?? 50;

    if (!Number.isInteger(limit) || limit < 1 || limit > 200) {
        throw new Error("AI 경보 조회 개수는 1~200이어야 합니다.");
    }

    if (
        query.droneId !== undefined &&
        (!Number.isInteger(query.droneId) || query.droneId < 1)
    ) {
        throw new Error("AI 경보 조회 드론 ID가 올바르지 않습니다.");
    }

    if (query.sessionId && query.sessionId.trim().length > 36) {
        throw new Error("AI 경보 세션 ID는 36자 이하여야 합니다.");
    }

    if (query.from && !Number.isFinite(Date.parse(query.from))) {
        throw new Error("AI 경보 조회 시작 시각이 올바르지 않습니다.");
    }

    if (query.to && !Number.isFinite(Date.parse(query.to))) {
        throw new Error("AI 경보 조회 종료 시각이 올바르지 않습니다.");
    }

    if (
        query.from &&
        query.to &&
        Date.parse(query.from) > Date.parse(query.to)
    ) {
        throw new Error("AI 경보 조회 시작 시각은 종료 시각보다 늦을 수 없습니다.");
    }

    const searchParams = new URLSearchParams({ limit: String(limit) });

    if (query.droneId !== undefined) {
        searchParams.set("droneId", String(query.droneId));
    }

    if (query.sessionId?.trim()) {
        searchParams.set("sessionId", query.sessionId.trim());
    }

    if (query.severity) {
        searchParams.set("severity", query.severity);
    }

    if (query.status) {
        searchParams.set("status", query.status);
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
        // 응답 본문이 JSON이 아니면 HTTP 상태 문구를 사용합니다.
    }

    return `HTTP ${response.status} ${response.statusText}`;
}

export async function getAiAlerts(
    query: AiAlertQuery = {},
): Promise<AiAlertItem[]> {
    const searchParams = buildSearchParams(query);
    const apiBaseUrl = getApiBaseUrl();
    let response: Response;

    try {
        response = await fetch(
            `${apiBaseUrl}/api/ai/alerts?${searchParams.toString()}`,
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

        throw new Error(`AI 경보 API 연결에 실패했습니다: ${message}`);
    }

    if (!response.ok) {
        throw new Error(
            `AI 경보 API 호출 실패: ${await readFailureMessage(response)}`,
        );
    }

    let body: unknown;

    try {
        body = await response.json();
    } catch {
        throw new Error("AI 경보 API 응답을 JSON으로 변환할 수 없습니다.");
    }

    const alerts = parseAiAlertList(body);

    if (!alerts) {
        throw new Error("AI 경보 API 응답 형식이 올바르지 않습니다.");
    }

    return alerts;
}
