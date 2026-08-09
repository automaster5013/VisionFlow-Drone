export const AUDIT_ACTIONS = [
    "FLIGHT_SESSION_STARTED",
    "FLIGHT_SESSION_UPDATED",
    "FLIGHT_SESSION_COMPLETED",
    "FLIGHT_SESSION_ABORTED",
    "FLIGHT_QUALITY_ASSESSED",
    "FLIGHT_QUALITY_INCIDENT_SYNCHRONIZED",
    "MAINTENANCE_WORK_ORDER_SYNCHRONIZED",
    "MAINTENANCE_INSPECTION_STARTED",
    "MAINTENANCE_RETURN_TO_SERVICE_APPROVED",
    "MAINTENANCE_DRONE_GROUNDED",
    "MAINTENANCE_FLIGHT_START_ALLOWED",
    "MAINTENANCE_FLIGHT_START_ADVISORY",
    "MAINTENANCE_FLIGHT_START_BLOCKED",
    "MAINTENANCE_FLIGHT_GATE_INCIDENT_SYNCHRONIZED",
    "GEOFENCE_CREATED",
    "GEOFENCE_UPDATED",
    "GEOFENCE_ACTIVATED",
    "GEOFENCE_DEACTIVATED",
    "INCIDENT_ASSIGNED",
    "INCIDENT_PRIORITY_CHANGED",
    "INCIDENT_STATUS_CHANGED",
    "INCIDENT_NOTE_ADDED",
    "DEMO_SCENARIO_STARTED",
    "DEMO_SCENARIO_DETECTED",
    "DEMO_SCENARIO_ESCALATED",
    "DEMO_SCENARIO_RESOLVED",
    "DEMO_SCENARIO_COMPLETED",
    "OPERATOR_LOGIN_SUCCEEDED",
    "OPERATOR_LOGIN_FAILED",
    "OPERATOR_LOGIN_LOCKED",
    "OPERATOR_PAIRING_CREATED",
    "OPERATOR_PAIRING_CLAIMED",
    "OPERATOR_PAIRING_APPROVED",
    "OPERATOR_PAIRING_SESSION_ISSUED",
    "OPERATOR_PAIRING_CANCELLED",
    "OPERATOR_LOGOUT",
    "OPERATOR_SESSION_REVOKED",
    "OPERATOR_SESSIONS_BULK_REVOKED",
    "AUDIT_LOG_EXPORTED",
    "AUDIT_LOG_RETENTION_EXECUTED",
] as const;

export const AUDIT_ENTITY_TYPES = [
    "FLIGHT_SESSION",
    "FLIGHT_QUALITY_ASSESSMENT",
    "MAINTENANCE_WORK_ORDER",
    "MAINTENANCE_FLIGHT_GATE",
    "GEOFENCE",
    "INCIDENT",
    "DEMO_SCENARIO",
    "OPERATOR_SESSION",
    "AUDIT_LOG",
] as const;

export type AuditAction = (typeof AUDIT_ACTIONS)[number];
export type AuditEntityType = (typeof AUDIT_ENTITY_TYPES)[number];

export interface AuditLogQuery {
    action?: AuditAction;
    entityType?: AuditEntityType;
    entityId?: string;
    actor?: string;
    from?: string;
    to?: string;
    page?: number;
    size?: number;
}

export interface AuditLogItem {
    id: number;
    occurredAt: string;
    actor: string;
    action: AuditAction;
    entityType: AuditEntityType;
    entityId: string;
    summary: string;
    detailsJson: string | null;
    requestMethod: string | null;
    requestPath: string | null;
    traceId: string;
}

export interface AuditLogPage {
    content: AuditLogItem[];
    page: number;
    size: number;
    totalElements: number;
    totalPages: number;
    first: boolean;
    last: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

function isNonNegativeInteger(value: unknown): value is number {
    return (
        typeof value === "number" &&
        Number.isInteger(value) &&
        value >= 0
    );
}

function isNullableString(value: unknown): value is string | null {
    return typeof value === "string" || value === null;
}

export function isAuditAction(value: unknown): value is AuditAction {
    return (
        typeof value === "string" &&
        (AUDIT_ACTIONS as readonly string[]).includes(value)
    );
}

export function isAuditEntityType(
    value: unknown,
): value is AuditEntityType {
    return (
        typeof value === "string" &&
        (AUDIT_ENTITY_TYPES as readonly string[]).includes(value)
    );
}

function isAuditLogItem(value: unknown): value is AuditLogItem {
    if (!isRecord(value)) {
        return false;
    }

    return (
        isNonNegativeInteger(value.id) &&
        typeof value.occurredAt === "string" &&
        typeof value.actor === "string" &&
        isAuditAction(value.action) &&
        isAuditEntityType(value.entityType) &&
        typeof value.entityId === "string" &&
        typeof value.summary === "string" &&
        isNullableString(value.detailsJson) &&
        isNullableString(value.requestMethod) &&
        isNullableString(value.requestPath) &&
        typeof value.traceId === "string"
    );
}

function unwrapData(value: unknown): unknown {
    return isRecord(value) && "data" in value ? value.data : value;
}

export function parseAuditLogPage(value: unknown): AuditLogPage | null {
    const candidate = unwrapData(value);

    if (!isRecord(candidate)) {
        return null;
    }

    if (
        !Array.isArray(candidate.content) ||
        !candidate.content.every(isAuditLogItem) ||
        !isNonNegativeInteger(candidate.page) ||
        !isNonNegativeInteger(candidate.size) ||
        !isNonNegativeInteger(candidate.totalElements) ||
        !isNonNegativeInteger(candidate.totalPages) ||
        typeof candidate.first !== "boolean" ||
        typeof candidate.last !== "boolean"
    ) {
        return null;
    }

    return {
        content: candidate.content,
        page: candidate.page,
        size: candidate.size,
        totalElements: candidate.totalElements,
        totalPages: candidate.totalPages,
        first: candidate.first,
        last: candidate.last,
    };
}
