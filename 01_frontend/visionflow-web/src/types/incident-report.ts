import {
    parseIncidentDetail,
    type IncidentActionHistoryItem,
    type IncidentContext,
    type IncidentItem,
} from "@/types/incident";

export interface IncidentReportMetrics {
    responseStartedAt: string | null;
    resolvedAt: string | null;
    closedAt: string | null;
    firstResponseSeconds: number | null;
    resolutionSeconds: number | null;
    actionCount: number;
    noteCount: number;
    evidenceAvailable: boolean;
}

export interface IncidentReport {
    generatedAt: string;
    incident: IncidentItem;
    context: IncidentContext;
    metrics: IncidentReportMetrics;
    history: IncidentActionHistoryItem[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

function isNullableString(value: unknown): value is string | null {
    return typeof value === "string" || value === null;
}

function isNullableFiniteNumber(value: unknown): value is number | null {
    return value === null ||
        (typeof value === "number" && Number.isFinite(value));
}

function isMetrics(value: unknown): value is IncidentReportMetrics {
    if (!isRecord(value)) {
        return false;
    }

    return (
        isNullableString(value.responseStartedAt) &&
        isNullableString(value.resolvedAt) &&
        isNullableString(value.closedAt) &&
        isNullableFiniteNumber(value.firstResponseSeconds) &&
        isNullableFiniteNumber(value.resolutionSeconds) &&
        typeof value.actionCount === "number" &&
        Number.isInteger(value.actionCount) &&
        value.actionCount >= 0 &&
        typeof value.noteCount === "number" &&
        Number.isInteger(value.noteCount) &&
        value.noteCount >= 0 &&
        typeof value.evidenceAvailable === "boolean"
    );
}

export function parseIncidentReport(value: unknown): IncidentReport | null {
    const unwrapped = isRecord(value) && "data" in value ? value.data : value;

    if (!isRecord(unwrapped) || typeof unwrapped.generatedAt !== "string") {
        return null;
    }

    const detail = parseIncidentDetail({
        incident: unwrapped.incident,
        context: unwrapped.context,
        history: unwrapped.history,
    });

    if (!detail || !isMetrics(unwrapped.metrics)) {
        return null;
    }

    return {
        generatedAt: unwrapped.generatedAt,
        incident: detail.incident,
        context: detail.context,
        metrics: unwrapped.metrics,
        history: detail.history,
    };
}
