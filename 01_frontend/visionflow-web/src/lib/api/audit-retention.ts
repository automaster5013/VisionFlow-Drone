import "server-only";

import {
    parseAuditRetentionStatus,
    type AuditRetentionStatus,
} from "@/types/audit-retention";

const DEFAULT_API_URL = "http://localhost:8080";

function getApiBaseUrl(): string {
    return (
        process.env.SPRING_API_URL ??
        process.env.BACKEND_API_URL ??
        process.env.API_BASE_URL ??
        DEFAULT_API_URL
    ).replace(/\/$/, "");
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

export async function getAuditRetentionStatus(): Promise<AuditRetentionStatus> {
    let response: Response;
    try {
        response = await fetch(`${getApiBaseUrl()}/api/audit-logs/retention`, {
            method: "GET",
            headers: { Accept: "application/json" },
            cache: "no-store",
            signal: AbortSignal.timeout(5_000),
        });
    } catch (error) {
        const message =
            error instanceof Error ? error.message : "Unknown connection error";
        throw new Error(`감사 보존 정책 API 연결에 실패했습니다: ${message}`);
    }
    if (!response.ok) {
        throw new Error(
            `감사 보존 정책 API 호출 실패: ${await readFailureMessage(response)}`,
        );
    }
    let body: unknown;
    try {
        body = await response.json();
    } catch {
        throw new Error("감사 보존 정책 응답을 JSON으로 변환할 수 없습니다.");
    }
    const result = parseAuditRetentionStatus(body);
    if (!result) {
        throw new Error("감사 보존 정책 API 응답 형식이 올바르지 않습니다.");
    }
    return result;
}
