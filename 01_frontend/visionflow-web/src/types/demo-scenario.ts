import type { IncidentContext } from "@/types/incident";

export type DemoScenarioStage =
    | "READY"
    | "DETECTED"
    | "ESCALATED"
    | "RESOLVED"
    | "COMPLETED";

export interface DemoScenario {
    scenarioId: string;
    droneId: number;
    flightSessionId: string;
    aiEventId: number | null;
    aiAlertId: number | null;
    incidentId: number | null;
    stage: DemoScenarioStage;
    lastMessage: string;
    startedAt: string;
    updatedAt: string;
    completedAt: string | null;
    incidentContext: IncidentContext | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

function isFiniteNumber(value: unknown): value is number {
    return typeof value === "number" && Number.isFinite(value);
}

function isNullableNumber(value: unknown): value is number | null {
    return value === null || isFiniteNumber(value);
}

function isNullableString(value: unknown): value is string | null {
    return value === null || typeof value === "string";
}

function isStage(value: unknown): value is DemoScenarioStage {
    return (
        value === "READY" ||
        value === "DETECTED" ||
        value === "ESCALATED" ||
        value === "RESOLVED" ||
        value === "COMPLETED"
    );
}

function isIncidentContext(value: unknown): value is IncidentContext {
    if (!isRecord(value)) {
        return false;
    }

    return (
        isFiniteNumber(value.incidentId) &&
        isFiniteNumber(value.droneId) &&
        isNullableString(value.sessionId) &&
        typeof value.occurredAt === "string" &&
        typeof value.replayAvailable === "boolean" &&
        (value.locationSource === "GEOFENCE_EVENT" ||
            value.locationSource === "NEAREST_TELEMETRY" ||
            value.locationSource === "UNAVAILABLE") &&
        isNullableNumber(value.latitude) &&
        isNullableNumber(value.longitude) &&
        isNullableNumber(value.altitude) &&
        isNullableString(value.locationRecordedAt) &&
        isNullableNumber(value.aiEventId) &&
        typeof value.snapshotAvailable === "boolean" &&
        isNullableString(value.snapshotUrl)
    );
}

export function parseDemoScenario(value: unknown): DemoScenario | null {
    const candidate =
        isRecord(value) && "data" in value ? value.data : value;

    if (!isRecord(candidate)) {
        return null;
    }

    return typeof candidate.scenarioId === "string" &&
        isFiniteNumber(candidate.droneId) &&
        typeof candidate.flightSessionId === "string" &&
        isNullableNumber(candidate.aiEventId) &&
        isNullableNumber(candidate.aiAlertId) &&
        isNullableNumber(candidate.incidentId) &&
        isStage(candidate.stage) &&
        typeof candidate.lastMessage === "string" &&
        typeof candidate.startedAt === "string" &&
        typeof candidate.updatedAt === "string" &&
        isNullableString(candidate.completedAt) &&
        (candidate.incidentContext === null ||
            isIncidentContext(candidate.incidentContext))
        ? (candidate as unknown as DemoScenario)
        : null;
}
