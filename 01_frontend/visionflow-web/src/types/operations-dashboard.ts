export type DashboardFlightSessionStatus =
    | "READY"
    | "ACTIVE"
    | "COMPLETED"
    | "ABORTED";

export interface DashboardFilterFormValues {
    droneId: string;
    status: "" | DashboardFlightSessionStatus;
    from: string;
    to: string;
    limit: "5" | "10" | "20";
}

export interface DashboardAppliedFilters {
    droneId: number | null;
    status: DashboardFlightSessionStatus | null;
    from: string | null;
    to: string | null;
    limit: number;
}

export interface OperationsDashboardQuery {
    droneId?: number;
    status?: DashboardFlightSessionStatus;
    from?: string;
    to?: string;
    limit?: number;
}

export interface DashboardFlightSessionStatistics {
    total: number;
    ready: number;
    active: number;
    completed: number;
    aborted: number;
}

export interface DashboardAiInferenceStatistics {
    totalEvents: number;
    detectedEvents: number;
    totalDetections: number;
}

export type DashboardFlightGateAction =
    | "MAINTENANCE_FLIGHT_START_ALLOWED"
    | "MAINTENANCE_FLIGHT_START_ADVISORY"
    | "MAINTENANCE_FLIGHT_START_BLOCKED";

export interface DashboardFlightGateStatistics {
    total: number;
    allowed: number;
    advisory: number;
    blocked: number;
}

export interface DashboardFlightSessionItem {
    sessionId: string;
    droneId: number;
    name: string;
    description: string | null;
    status: DashboardFlightSessionStatus;
    sourceDeviceId: string | null;
    startedAt: string;
    endedAt: string | null;
    durationSeconds: number;
}

export interface DashboardAiAlertItem {
    eventId: number;
    droneId: number;
    sessionId: string;
    sourceId: string;
    sourceType: string;
    frameIndex: number;
    capturedAt: string;
    detectionCount: number;
    snapshotAvailable: boolean;
}

export interface DashboardFlightGateDecisionItem {
    auditId: number;
    droneId: number;
    action: DashboardFlightGateAction;
    summary: string;
    occurredAt: string;
}

export interface OperationsDashboardData {
    generatedAt: string;
    filters: DashboardAppliedFilters;
    flightSessions: DashboardFlightSessionStatistics;
    aiInference: DashboardAiInferenceStatistics;
    flightGate: DashboardFlightGateStatistics;
    recentSessions: DashboardFlightSessionItem[];
    recentAbortedSessions: DashboardFlightSessionItem[];
    recentAiAlerts: DashboardAiAlertItem[];
    recentFlightGateDecisions: DashboardFlightGateDecisionItem[];
}
