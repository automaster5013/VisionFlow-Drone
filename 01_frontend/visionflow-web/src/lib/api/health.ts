import type { ApiResponse, HealthData } from "@/types/health";

const DEFAULT_API_URL = "http://localhost:8080";

function getApiBaseUrl(): string {
    return process.env.SPRING_API_URL ?? DEFAULT_API_URL;
}

export async function getBackendHealth(): Promise<HealthData> {
    const apiBaseUrl = getApiBaseUrl();

    let response: Response;

    try {
        response = await fetch(`${apiBaseUrl}/api/health`, {
            method: "GET",
            headers: {
                Accept: "application/json",
            },

            // 관제 상태는 오래 캐시하면 안 되므로 매번 새로 조회합니다.
            cache: "no-store",

            // 연결이 지나치게 오래 걸리는 상황을 방지합니다.
            signal: AbortSignal.timeout(5000),
        });
    } catch (error) {
        const message =
            error instanceof Error ? error.message : "Unknown connection error";

        throw new Error(`Spring Boot 연결에 실패했습니다: ${message}`);
    }

    if (!response.ok) {
        throw new Error(
            `Health API 호출 실패: HTTP ${response.status} ${response.statusText}`,
        );
    }

    let body: ApiResponse<HealthData>;

    try {
        body = (await response.json()) as ApiResponse<HealthData>;
    } catch {
        throw new Error("Health API 응답을 JSON으로 변환할 수 없습니다.");
    }

    if (!body.success || !body.data) {
        throw new Error("Health API가 정상적인 데이터 구조를 반환하지 않았습니다.");
    }

    return body.data;
}