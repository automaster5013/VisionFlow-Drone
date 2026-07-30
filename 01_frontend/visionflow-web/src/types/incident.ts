export type IncidentSourceType =
    | "AI_ALERT"
    | "GEOFENCE"
    | "FLIGHT_QUALITY"
    | "FLIGHT_GATE";

export type IncidentPriority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type IncidentStatus =
    | "OPEN"
    | "IN_PROGRESS"
    | "RESOLVED"
    | "CLOSED";

export type IncidentActionType =
    | "CREATED"
    | "ASSIGNED"
    | "PRIORITY_CHANGED"
    | "STATUS_CHANGED"
    | "NOTE_ADDED"
    | "SOURCE_SYNCHRONIZED"
    | "SLA_ESCALATED";

export type IncidentLocationSource =
    | "GEOFENCE_EVENT"
    | "NEAREST_TELEMETRY"
    | "UNAVAILABLE";

export interface IncidentQuery {
    droneId?: number;
    sourceType?: IncidentSourceType;
    priority?: IncidentPriority;
    status?: IncidentStatus;
    assignee?: string;
    from?: string;
    to?: string;
    limit?: number;
}

export interface IncidentItem {
    id: number;
    sourceType: IncidentSourceType;
    sourceId: number;
    droneId: number;
    sessionId: string | null;
    priority: IncidentPriority;
    status: IncidentStatus;
    title: string;
    summary: string;
    assignee: string | null;
    assignedBy: string | null;
    assignedAt: string | null;
    occurredAt: string;
    resolvedAt: string | null;
    closedAt: string | null;
    slaDueAt: string | null;
    slaBreachedAt: string | null;
    escalationLevel: number;
    createdAt: string;
    updatedAt: string;
}

export interface IncidentActionHistoryItem {
    id: number;
    actionType: IncidentActionType;
    previousStatus: IncidentStatus | null;
    newStatus: IncidentStatus | null;
    actor: string;
    note: string | null;
    createdAt: string;
}

export interface IncidentDetail {
    incident: IncidentItem;
    history: IncidentActionHistoryItem[];
    context: IncidentContext;
}

export interface IncidentContext {
    incidentId: number;
    droneId: number;
    sessionId: string | null;
    occurredAt: string;
    replayAvailable: boolean;
    locationSource: IncidentLocationSource;
    latitude: number | null;
    longitude: number | null;
    altitude: number | null;
    locationRecordedAt: string | null;
    aiEventId: number | null;
    snapshotAvailable: boolean;
    snapshotUrl: string | null;
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

function isSourceType(value: unknown): value is IncidentSourceType {
    return (
        value === "AI_ALERT" ||
        value === "GEOFENCE" ||
        value === "FLIGHT_QUALITY" ||
        value === "FLIGHT_GATE"
    );
}

function isPriority(value: unknown): value is IncidentPriority {
    return (
        value === "LOW" ||
        value === "MEDIUM" ||
        value === "HIGH" ||
        value === "CRITICAL"
    );
}

function isStatus(value: unknown): value is IncidentStatus {
    return (
        value === "OPEN" ||
        value === "IN_PROGRESS" ||
        value === "RESOLVED" ||
        value === "CLOSED"
    );
}

function isActionType(value: unknown): value is IncidentActionType {
    return (
        value === "CREATED" ||
        value === "ASSIGNED" ||
        value === "PRIORITY_CHANGED" ||
        value === "STATUS_CHANGED" ||
        value === "NOTE_ADDED" ||
        value === "SOURCE_SYNCHRONIZED" ||
        value === "SLA_ESCALATED"
    );
}

function isLocationSource(value: unknown): value is IncidentLocationSource {
    return (
        value === "GEOFENCE_EVENT" ||
        value === "NEAREST_TELEMETRY" ||
        value === "UNAVAILABLE"
    );
}

function unwrapData(value: unknown): unknown {
    return isRecord(value) && "data" in value ? value.data : value;
}

export function isIncidentItem(value: unknown): value is IncidentItem {
    if (!isRecord(value)) {
        return false;
    }

    return (
        isFiniteNumber(value.id) &&
        isSourceType(value.sourceType) &&
        isFiniteNumber(value.sourceId) &&
        isFiniteNumber(value.droneId) &&
        isNullableString(value.sessionId) &&
        isPriority(value.priority) &&
        isStatus(value.status) &&
        typeof value.title === "string" &&
        typeof value.summary === "string" &&
        isNullableString(value.assignee) &&
        isNullableString(value.assignedBy) &&
        isNullableString(value.assignedAt) &&
        typeof value.occurredAt === "string" &&
        isNullableString(value.resolvedAt) &&
        isNullableString(value.closedAt) &&
        isNullableString(value.slaDueAt) &&
        isNullableString(value.slaBreachedAt) &&
        isFiniteNumber(value.escalationLevel) &&
        Number.isInteger(value.escalationLevel) &&
        value.escalationLevel >= 0 &&
        typeof value.createdAt === "string" &&
        typeof value.updatedAt === "string"
    );
}

function isHistoryItem(value: unknown): value is IncidentActionHistoryItem {
    if (!isRecord(value)) {
        return false;
    }

    return (
        isFiniteNumber(value.id) &&
        isActionType(value.actionType) &&
        (value.previousStatus === null || isStatus(value.previousStatus)) &&
        (value.newStatus === null || isStatus(value.newStatus)) &&
        typeof value.actor === "string" &&
        isNullableString(value.note) &&
        typeof value.createdAt === "string"
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
        isLocationSource(value.locationSource) &&
        (value.latitude === null || isFiniteNumber(value.latitude)) &&
        (value.longitude === null || isFiniteNumber(value.longitude)) &&
        (value.altitude === null || isFiniteNumber(value.altitude)) &&
        isNullableString(value.locationRecordedAt) &&
        (value.aiEventId === null || isFiniteNumber(value.aiEventId)) &&
        typeof value.snapshotAvailable === "boolean" &&
        isNullableString(value.snapshotUrl)
    );
}

export function parseIncidentList(value: unknown): IncidentItem[] | null {
    const candidate = unwrapData(value);

    return Array.isArray(candidate) && candidate.every(isIncidentItem)
        ? candidate
        : null;
}

export function parseIncidentItem(value: unknown): IncidentItem | null {
    const candidate = unwrapData(value);
    return isIncidentItem(candidate) ? candidate : null;
}

export function parseIncidentDetail(value: unknown): IncidentDetail | null {
    const candidate = unwrapData(value);

    if (!isRecord(candidate)) {
        return null;
    }

    return isIncidentItem(candidate.incident) &&
        Array.isArray(candidate.history) &&
        candidate.history.every(isHistoryItem) &&
        isIncidentContext(candidate.context)
        ? {
              incident: candidate.incident,
              history: candidate.history,
              context: candidate.context,
          }
        : null;
}
