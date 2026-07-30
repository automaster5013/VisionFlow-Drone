import type { Metadata } from "next";

import { AiAlertOperationsPanel } from "@/components/dashboard/ai-alert-operations-panel";
import { AiAlertRealtimeNotifier } from "@/components/dashboard/ai-alert-realtime-notifier";
import { FleetReliabilityAttentionPanel } from "@/components/dashboard/fleet-reliability-attention-panel";
import { HealthDashboard } from "@/components/dashboard/health-dashboard";
import { IncidentOperationsPanel } from "@/components/dashboard/incident-operations-panel";
import { MobileSensorEvidenceCard } from "@/components/dashboard/mobile-sensor-evidence-card";
import { OperationsDashboard } from "@/components/dashboard/operations-dashboard";
import { getAiAlerts } from "@/lib/api/ai-alerts";
import { getFleetReliability } from "@/lib/api/fleet-reliability";
import { getBackendHealth } from "@/lib/api/health";
import { getIncidents } from "@/lib/api/incidents";
import { getOperationsDashboard } from "@/lib/api/operations-dashboard";
import { loadMobileEvidenceStatus } from "@/lib/mobile-evidence";
import type { AiAlertItem, AiAlertQuery } from "@/types/ai-alert";
import type { IncidentItem, IncidentQuery } from "@/types/incident";
import type { FleetReliabilityResponse } from "@/types/fleet-reliability";
import type {
    DashboardFilterFormValues,
    DashboardFlightSessionStatus,
    OperationsDashboardData,
    OperationsDashboardQuery,
} from "@/types/operations-dashboard";

export const metadata: Metadata = {
    title: "운영 대시보드",
};

export const dynamic = "force-dynamic";

type SearchValue = string | string[] | undefined;

interface DashboardPageProps {
    searchParams: Promise<Record<string, SearchValue>>;
}

interface OperationsLoadResult {
    data: OperationsDashboardData | null;
    errorMessage: string | null;
}

interface AiAlertsLoadResult {
    alerts: AiAlertItem[];
    errorMessage: string | null;
}

interface IncidentsLoadResult {
    incidents: IncidentItem[];
    errorMessage: string | null;
}

interface FleetReliabilityLoadResult {
    data: FleetReliabilityResponse | null;
    errorMessage: string | null;
}

interface ParsedDashboardFilters {
    formValues: DashboardFilterFormValues;
    query: OperationsDashboardQuery;
    errorMessage: string | null;
}

function firstSearchValue(value: SearchValue): string {
    return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

function isDateInput(value: string): boolean {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
        return false;
    }

    const [year, month, day] = value.split("-").map(Number);
    const date = new Date(Date.UTC(year, month - 1, day));

    return (
        date.getUTCFullYear() === year &&
        date.getUTCMonth() === month - 1 &&
        date.getUTCDate() === day
    );
}

function isSessionStatus(
    value: string,
): value is DashboardFlightSessionStatus {
    return (
        value === "READY" ||
        value === "ACTIVE" ||
        value === "COMPLETED" ||
        value === "ABORTED"
    );
}

function parseDashboardFilters(
    searchParams: Record<string, SearchValue>,
): ParsedDashboardFilters {
    const rawDroneId = firstSearchValue(searchParams.droneId);
    const rawStatus = firstSearchValue(searchParams.status);
    const rawFrom = firstSearchValue(searchParams.from);
    const rawTo = firstSearchValue(searchParams.to);
    const rawLimit = firstSearchValue(searchParams.limit);

    const status = isSessionStatus(rawStatus) ? rawStatus : "";
    const limit = rawLimit === "10" || rawLimit === "20" ? rawLimit : "5";
    const formValues: DashboardFilterFormValues = {
        droneId: rawDroneId,
        status,
        from: rawFrom,
        to: rawTo,
        limit,
    };

    if (rawDroneId && (!/^\d+$/.test(rawDroneId) || Number(rawDroneId) < 1)) {
        return {
            formValues,
            query: {},
            errorMessage: "드론 ID는 1 이상의 정수여야 합니다.",
        };
    }

    if (rawStatus && !status) {
        return {
            formValues,
            query: {},
            errorMessage: "지원하지 않는 비행 세션 상태입니다.",
        };
    }

    if (rawFrom && !isDateInput(rawFrom)) {
        return {
            formValues,
            query: {},
            errorMessage: "조회 시작일이 올바르지 않습니다.",
        };
    }

    if (rawTo && !isDateInput(rawTo)) {
        return {
            formValues,
            query: {},
            errorMessage: "조회 종료일이 올바르지 않습니다.",
        };
    }

    if (rawFrom && rawTo && rawFrom > rawTo) {
        return {
            formValues,
            query: {},
            errorMessage: "조회 시작일은 종료일보다 늦을 수 없습니다.",
        };
    }

    if (rawLimit && rawLimit !== "5" && rawLimit !== "10" && rawLimit !== "20") {
        return {
            formValues,
            query: {},
            errorMessage: "최근 목록 개수는 5, 10, 20 중 하나여야 합니다.",
        };
    }

    return {
        formValues,
        query: {
            droneId: rawDroneId ? Number(rawDroneId) : undefined,
            status: status || undefined,
            from: rawFrom ? `${rawFrom}T00:00:00+09:00` : undefined,
            to: rawTo ? `${rawTo}T23:59:59.999+09:00` : undefined,
            limit: Number(limit),
        },
        errorMessage: null,
    };
}

function toAiAlertQuery(query: OperationsDashboardQuery): AiAlertQuery {
    return {
        droneId: query.droneId,
        from: query.from,
        to: query.to,
        limit: 50,
    };
}

function toIncidentQuery(query: OperationsDashboardQuery): IncidentQuery {
    return {
        droneId: query.droneId,
        from: query.from,
        to: query.to,
        limit: 100,
    };
}

async function loadOperations(
    query: OperationsDashboardQuery,
    validationError: string | null,
): Promise<OperationsLoadResult> {
    if (validationError) {
        return {
            data: null,
            errorMessage: validationError,
        };
    }

    try {
        return {
            data: await getOperationsDashboard(query),
            errorMessage: null,
        };
    } catch (error) {
        return {
            data: null,
            errorMessage:
                error instanceof Error
                    ? error.message
                    : "운영 집계를 불러오지 못했습니다.",
        };
    }
}

async function loadAiAlerts(
    query: AiAlertQuery,
    validationError: string | null,
): Promise<AiAlertsLoadResult> {
    if (validationError) {
        return {
            alerts: [],
            errorMessage: validationError,
        };
    }

    try {
        return {
            alerts: await getAiAlerts(query),
            errorMessage: null,
        };
    } catch (error) {
        return {
            alerts: [],
            errorMessage:
                error instanceof Error
                    ? error.message
                    : "AI 경보를 불러오지 못했습니다.",
        };
    }
}

async function loadIncidents(
    query: IncidentQuery,
    validationError: string | null,
): Promise<IncidentsLoadResult> {
    if (validationError) {
        return {
            incidents: [],
            errorMessage: validationError,
        };
    }

    try {
        return {
            incidents: await getIncidents(query),
            errorMessage: null,
        };
    } catch (error) {
        return {
            incidents: [],
            errorMessage:
                error instanceof Error
                    ? error.message
                    : "Incident를 불러오지 못했습니다.",
        };
    }
}

async function loadFleetReliability(): Promise<FleetReliabilityLoadResult> {
    try {
        return {
            data: await getFleetReliability(20),
            errorMessage: null,
        };
    } catch (error) {
        return {
            data: null,
            errorMessage:
                error instanceof Error
                    ? error.message
                    : "함대 운영 신뢰도를 불러오지 못했습니다.",
        };
    }
}

export default async function DashboardPage({
    searchParams,
}: DashboardPageProps) {
    const parsedFilters = parseDashboardFilters(await searchParams);
    const aiAlertQuery = toAiAlertQuery(parsedFilters.query);
    const incidentQuery = toIncidentQuery(parsedFilters.query);
    const [
        health,
        operations,
        aiAlerts,
        incidents,
        fleetReliability,
        mobileEvidence,
    ] = await Promise.all([
        getBackendHealth(),
        loadOperations(parsedFilters.query, parsedFilters.errorMessage),
        loadAiAlerts(aiAlertQuery, parsedFilters.errorMessage),
        loadIncidents(incidentQuery, parsedFilters.errorMessage),
        loadFleetReliability(),
        loadMobileEvidenceStatus(),
    ]);

    return (
        <div className="space-y-10">
            <OperationsDashboard
                data={operations.data}
                errorMessage={operations.errorMessage}
                filterValues={parsedFilters.formValues}
            />
            <MobileSensorEvidenceCard status={mobileEvidence} />
            <FleetReliabilityAttentionPanel
                data={fleetReliability.data}
                errorMessage={fleetReliability.errorMessage}
            />
            <AiAlertRealtimeNotifier query={aiAlertQuery} />
            <IncidentOperationsPanel
                initialIncidents={incidents.incidents}
                initialError={incidents.errorMessage}
                initialQuery={incidentQuery}
            />
            <AiAlertOperationsPanel
                initialAlerts={aiAlerts.alerts}
                initialError={aiAlerts.errorMessage}
                initialQuery={aiAlertQuery}
            />
            <HealthDashboard health={health} />
        </div>
    );
}
