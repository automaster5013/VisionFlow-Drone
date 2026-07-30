import type {
    ApiResponse,
    Drone,
    DroneStatus,
} from "@/types/drone";

const DEFAULT_API_URL = "http://localhost:8080";

function getApiBaseUrl(): string {
    return process.env.SPRING_API_URL ?? DEFAULT_API_URL;
}

export async function getDrones(
    status?: DroneStatus,
): Promise<Drone[]> {
    const query = status
        ? `?status=${encodeURIComponent(status)}`
        : "";

    const response = await fetch(
        `${getApiBaseUrl()}/api/drones${query}`,
        {
            method: "GET",
            headers: {
                Accept: "application/json",
            },
            cache: "no-store",
        },
    );

    if (!response.ok) {
        throw new Error(
            `드론 목록 조회 실패: HTTP ${response.status}`,
        );
    }

    const body = (await response.json()) as ApiResponse<Drone[]>;

    return body.data;
}

export async function getDrone(
    id: string | number,
): Promise<Drone> {
    let response: Response;

    try {
        response = await fetch(
            `${getApiBaseUrl()}/api/drones/${id}`,
            {
                method: "GET",
                headers: {
                    Accept: "application/json",
                },
                cache: "no-store",
                signal: AbortSignal.timeout(5000),
            },
        );
    } catch (error) {
        const message =
            error instanceof Error
                ? error.message
                : "알 수 없는 연결 오류";

        throw new Error(
            `드론 상세 API 연결에 실패했습니다: ${message}`,
        );
    }

    if (response.status === 404) {
        throw new Error("DRONE_NOT_FOUND");
    }

    if (!response.ok) {
        throw new Error(
            `드론 상세 조회에 실패했습니다: HTTP ${response.status}`,
        );
    }

    const body = (await response.json()) as ApiResponse<Drone>;

    if (!body.success || !body.data) {
        throw new Error(
            "드론 상세 API가 올바른 응답을 반환하지 않았습니다.",
        );
    }

    return body.data;
}