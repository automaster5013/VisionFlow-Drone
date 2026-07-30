export type AiAlertSeverity = "INFO" | "WARNING" | "CRITICAL";

export type AiAlertStatus = "OPEN" | "ACKNOWLEDGED" | "RESOLVED";

export interface AiAlertQuery {
    droneId?: number;
    sessionId?: string;
    severity?: AiAlertSeverity;
    status?: AiAlertStatus;
    from?: string;
    to?: string;
    limit?: number;
}

export interface AiAlertItem {
    id: number;
    eventId: number;
    droneId: number;
    sessionId: string;
    severity: AiAlertSeverity;
    status: AiAlertStatus;
    title: string;
    summary: string;
    primaryClassName: string;
    maxConfidence: number;
    detectionCount: number;
    capturedAt: string;
    snapshotAvailable: boolean;
    snapshotUrl: string | null;
    acknowledgedAt: string | null;
    acknowledgedBy: string | null;
    resolvedAt: string | null;
    resolvedBy: string | null;
    resolutionNote: string | null;
    createdAt: string;
    updatedAt: string;
}

export interface AiAlertDetection {
    id: number;
    classId: number;
    className: string;
    confidence: number;
    x1: number;
    y1: number;
    x2: number;
    y2: number;
}

export interface AiAlertInferenceEvent {
    id: number;
    sourceId: string;
    sessionId: string;
    sourceType: string;
    droneId: number;
    frameIndex: number;
    capturedAt: string;
    receivedAt: string;
    inferenceMs: number;
    detectionCount: number;
    snapshotAvailable: boolean;
    snapshotUrl: string | null;
    snapshotSizeBytes: number | null;
    snapshotCreatedAt: string | null;
    detections: AiAlertDetection[];
}

export interface AiAlertDetail {
    alert: AiAlertItem;
    event: AiAlertInferenceEvent;
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

function isSeverity(value: unknown): value is AiAlertSeverity {
    return value === "INFO" || value === "WARNING" || value === "CRITICAL";
}

function isStatus(value: unknown): value is AiAlertStatus {
    return (
        value === "OPEN" ||
        value === "ACKNOWLEDGED" ||
        value === "RESOLVED"
    );
}

export function isAiAlertItem(value: unknown): value is AiAlertItem {
    if (!isRecord(value)) {
        return false;
    }

    return (
        isFiniteNumber(value.id) &&
        isFiniteNumber(value.eventId) &&
        isFiniteNumber(value.droneId) &&
        typeof value.sessionId === "string" &&
        isSeverity(value.severity) &&
        isStatus(value.status) &&
        typeof value.title === "string" &&
        typeof value.summary === "string" &&
        typeof value.primaryClassName === "string" &&
        isFiniteNumber(value.maxConfidence) &&
        isFiniteNumber(value.detectionCount) &&
        typeof value.capturedAt === "string" &&
        typeof value.snapshotAvailable === "boolean" &&
        isNullableString(value.snapshotUrl) &&
        isNullableString(value.acknowledgedAt) &&
        isNullableString(value.acknowledgedBy) &&
        isNullableString(value.resolvedAt) &&
        isNullableString(value.resolvedBy) &&
        isNullableString(value.resolutionNote) &&
        typeof value.createdAt === "string" &&
        typeof value.updatedAt === "string"
    );
}

function isDetection(value: unknown): value is AiAlertDetection {
    if (!isRecord(value)) {
        return false;
    }

    return (
        isFiniteNumber(value.id) &&
        isFiniteNumber(value.classId) &&
        typeof value.className === "string" &&
        isFiniteNumber(value.confidence) &&
        isFiniteNumber(value.x1) &&
        isFiniteNumber(value.y1) &&
        isFiniteNumber(value.x2) &&
        isFiniteNumber(value.y2)
    );
}

function isInferenceEvent(value: unknown): value is AiAlertInferenceEvent {
    if (!isRecord(value)) {
        return false;
    }

    return (
        isFiniteNumber(value.id) &&
        typeof value.sourceId === "string" &&
        typeof value.sessionId === "string" &&
        typeof value.sourceType === "string" &&
        isFiniteNumber(value.droneId) &&
        isFiniteNumber(value.frameIndex) &&
        typeof value.capturedAt === "string" &&
        typeof value.receivedAt === "string" &&
        isFiniteNumber(value.inferenceMs) &&
        isFiniteNumber(value.detectionCount) &&
        typeof value.snapshotAvailable === "boolean" &&
        isNullableString(value.snapshotUrl) &&
        (value.snapshotSizeBytes === null ||
            isFiniteNumber(value.snapshotSizeBytes)) &&
        isNullableString(value.snapshotCreatedAt) &&
        Array.isArray(value.detections) &&
        value.detections.every(isDetection)
    );
}

function unwrapData(value: unknown): unknown {
    return isRecord(value) && "data" in value ? value.data : value;
}

export function parseAiAlertList(value: unknown): AiAlertItem[] | null {
    const candidate = unwrapData(value);

    return Array.isArray(candidate) && candidate.every(isAiAlertItem)
        ? candidate
        : null;
}

export function parseAiAlertItem(value: unknown): AiAlertItem | null {
    const candidate = unwrapData(value);
    return isAiAlertItem(candidate) ? candidate : null;
}

export function parseAiAlertDetail(value: unknown): AiAlertDetail | null {
    const candidate = unwrapData(value);

    if (!isRecord(candidate)) {
        return null;
    }

    return isAiAlertItem(candidate.alert) && isInferenceEvent(candidate.event)
        ? {
              alert: candidate.alert,
              event: candidate.event,
          }
        : null;
}
