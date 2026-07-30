import type {
    DashboardAiAlertItem,
    DashboardAppliedFilters,
    DashboardFlightGateAction,
    DashboardFlightGateDecisionItem,
    DashboardFlightGateStatistics,
    DashboardFlightSessionItem,
    DashboardFlightSessionStatus,
    DashboardFlightSessionStatistics,
    OperationsDashboardData,
    OperationsDashboardQuery,
} from "@/types/operations-dashboard";

const DEFAULT_API_URL = "http://localhost:8080";

function getApiBaseUrl(): string {
    return (
        process.env.SPRING_API_URL ??
        process.env.BACKEND_API_URL ??
        process.env.API_BASE_URL ??
        DEFAULT_API_URL
    ).replace(/\/$/, "");
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

function isFiniteNumber(value: unknown): value is number {
    return typeof value === "number" && Number.isFinite(value);
}

function isNullableString(value: unknown): value is string | null {
    return typeof value === "string" || value === null;
}

function isFlightSessionStatus(
    value: unknown,
): value is DashboardFlightSessionStatus {
    return (
        value === "READY" ||
        value === "ACTIVE" ||
        value === "COMPLETED" ||
        value === "ABORTED"
    );
}

function isAppliedFilters(value: unknown): value is DashboardAppliedFilters {
    if (!isRecord(value)) {
        return false;
    }

    return (
        (value.droneId === null || isFiniteNumber(value.droneId)) &&
        (value.status === null || isFlightSessionStatus(value.status)) &&
        isNullableString(value.from) &&
        isNullableString(value.to) &&
        isFiniteNumber(value.limit)
    );
}

function isFlightSessionStatistics(
    value: unknown,
): value is DashboardFlightSessionStatistics {
    if (!isRecord(value)) {
        return false;
    }

    return (
        isFiniteNumber(value.total) &&
        isFiniteNumber(value.ready) &&
        isFiniteNumber(value.active) &&
        isFiniteNumber(value.completed) &&
        isFiniteNumber(value.aborted)
    );
}

function isAiInferenceStatistics(value: unknown): boolean {
    if (!isRecord(value)) {
        return false;
    }

    return (
        isFiniteNumber(value.totalEvents) &&
        isFiniteNumber(value.detectedEvents) &&
        isFiniteNumber(value.totalDetections)
    );
}

function isFlightGateAction(
    value: unknown,
): value is DashboardFlightGateAction {
    return (
        value === "MAINTENANCE_FLIGHT_START_ALLOWED" ||
        value === "MAINTENANCE_FLIGHT_START_ADVISORY" ||
        value === "MAINTENANCE_FLIGHT_START_BLOCKED"
    );
}

function isFlightGateStatistics(
    value: unknown,
): value is DashboardFlightGateStatistics {
    if (!isRecord(value)) {
        return false;
    }

    return (
        isFiniteNumber(value.total) &&
        isFiniteNumber(value.allowed) &&
        isFiniteNumber(value.advisory) &&
        isFiniteNumber(value.blocked)
    );
}

function isFlightSessionItem(
    value: unknown,
): value is DashboardFlightSessionItem {
    if (!isRecord(value)) {
        return false;
    }

    return (
        typeof value.sessionId === "string" &&
        isFiniteNumber(value.droneId) &&
        typeof value.name === "string" &&
        isNullableString(value.description) &&
        isFlightSessionStatus(value.status) &&
        isNullableString(value.sourceDeviceId) &&
        typeof value.startedAt === "string" &&
        isNullableString(value.endedAt) &&
        isFiniteNumber(value.durationSeconds)
    );
}

function isAiAlertItem(value: unknown): value is DashboardAiAlertItem {
    if (!isRecord(value)) {
        return false;
    }

    return (
        isFiniteNumber(value.eventId) &&
        isFiniteNumber(value.droneId) &&
        typeof value.sessionId === "string" &&
        typeof value.sourceId === "string" &&
        typeof value.sourceType === "string" &&
        isFiniteNumber(value.frameIndex) &&
        typeof value.capturedAt === "string" &&
        isFiniteNumber(value.detectionCount) &&
        typeof value.snapshotAvailable === "boolean"
    );
}

function isFlightGateDecisionItem(
    value: unknown,
): value is DashboardFlightGateDecisionItem {
    if (!isRecord(value)) {
        return false;
    }

    return (
        isFiniteNumber(value.auditId) &&
        isFiniteNumber(value.droneId) &&
        isFlightGateAction(value.action) &&
        typeof value.summary === "string" &&
        typeof value.occurredAt === "string"
    );
}

function isOperationsDashboardData(
    value: unknown,
): value is OperationsDashboardData {
    if (!isRecord(value)) {
        return false;
    }

    return (
        typeof value.generatedAt === "string" &&
        isAppliedFilters(value.filters) &&
        isFlightSessionStatistics(value.flightSessions) &&
        isAiInferenceStatistics(value.aiInference) &&
        isFlightGateStatistics(value.flightGate) &&
        Array.isArray(value.recentSessions) &&
        value.recentSessions.every(isFlightSessionItem) &&
        Array.isArray(value.recentAbortedSessions) &&
        value.recentAbortedSessions.every(isFlightSessionItem) &&
        Array.isArray(value.recentAiAlerts) &&
        value.recentAiAlerts.every(isAiAlertItem) &&
        Array.isArray(value.recentFlightGateDecisions) &&
        value.recentFlightGateDecisions.every(
            isFlightGateDecisionItem,
        )
    );
}

function unwrapDashboardData(value: unknown): OperationsDashboardData | null {
    if (isOperationsDashboardData(value)) {
        return value;
    }

    if (isRecord(value) && isOperationsDashboardData(value.data)) {
        return value.data;
    }

    return null;
}

export async function getOperationsDashboard(
    query: OperationsDashboardQuery = {},
): Promise<OperationsDashboardData> {
    const limit = query.limit ?? 5;

    if (!Number.isInteger(limit) || limit < 1 || limit > 20) {
        throw new Error("운영 대시보드 최근 항목 제한값이 올바르지 않습니다.");
    }

    if (
        query.droneId !== undefined &&
        (!Number.isInteger(query.droneId) || query.droneId < 1)
    ) {
        throw new Error("운영 대시보드 드론 ID가 올바르지 않습니다.");
    }

    if (query.from && !Number.isFinite(Date.parse(query.from))) {
        throw new Error("운영 대시보드 시작 시각이 올바르지 않습니다.");
    }

    if (query.to && !Number.isFinite(Date.parse(query.to))) {
        throw new Error("운영 대시보드 종료 시각이 올바르지 않습니다.");
    }

    if (
        query.from &&
        query.to &&
        Date.parse(query.from) > Date.parse(query.to)
    ) {
        throw new Error("조회 시작일은 종료일보다 늦을 수 없습니다.");
    }

    const searchParams = new URLSearchParams({ limit: String(limit) });

    if (query.droneId !== undefined) {
        searchParams.set("droneId", String(query.droneId));
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

    const apiBaseUrl = getApiBaseUrl();
    let response: Response;

    try {
        response = await fetch(
            `${apiBaseUrl}/api/dashboard/operations?${searchParams}`,
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
            error instanceof Error ? error.message : "Unknown connection error";

        throw new Error(`운영 대시보드 API 연결에 실패했습니다: ${message}`);
    }

    if (!response.ok) {
        throw new Error(
            `운영 대시보드 API 호출 실패: HTTP ${response.status} ${response.statusText}`,
        );
    }

    let body: unknown;

    try {
        body = await response.json();
    } catch {
        throw new Error("운영 대시보드 응답을 JSON으로 변환할 수 없습니다.");
    }

    const data = unwrapDashboardData(body);

    if (!data) {
        throw new Error("운영 대시보드 API 응답 형식이 올바르지 않습니다.");
    }

    return data;
}
