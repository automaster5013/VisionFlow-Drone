import { isIncidentItem, type IncidentItem } from "@/types/incident";

export type IncidentRealtimeAction =
    | "CREATED"
    | "ASSIGNED"
    | "PRIORITY_CHANGED"
    | "STATUS_CHANGED"
    | "NOTE_ADDED"
    | "SOURCE_SYNCHRONIZED"
    | "SLA_ESCALATED";

export type IncidentRealtimeConnectionStatus =
    | "CONNECTING"
    | "CONNECTED"
    | "DISCONNECTED"
    | "ERROR";

export interface IncidentRealtimeMessage {
    action: IncidentRealtimeAction;
    incident: IncidentItem;
    publishedAt: string;
}

function isRealtimeAction(value: unknown): value is IncidentRealtimeAction {
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

export function parseIncidentRealtimeMessage(
    value: unknown,
): IncidentRealtimeMessage | null {
    if (typeof value !== "object" || value === null) {
        return null;
    }

    const candidate = value as Partial<IncidentRealtimeMessage>;

    return isRealtimeAction(candidate.action) &&
        isIncidentItem(candidate.incident) &&
        typeof candidate.publishedAt === "string"
        ? {
              action: candidate.action,
              incident: candidate.incident,
              publishedAt: candidate.publishedAt,
          }
        : null;
}
