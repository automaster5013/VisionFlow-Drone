import { isAiAlertItem, type AiAlertItem } from "@/types/ai-alert";

export type AiAlertRealtimeAction =
    | "CREATED"
    | "ACKNOWLEDGED"
    | "RESOLVED";

export interface AiAlertRealtimeMessage {
    action: AiAlertRealtimeAction;
    occurredAt: string;
    alert: AiAlertItem;
}

export type AiAlertRealtimeConnectionStatus =
    | "CONNECTING"
    | "CONNECTED"
    | "DISCONNECTED"
    | "ERROR";

function isRealtimeAction(value: unknown): value is AiAlertRealtimeAction {
    return (
        value === "CREATED" ||
        value === "ACKNOWLEDGED" ||
        value === "RESOLVED"
    );
}

export function parseAiAlertRealtimeMessage(
    value: unknown,
): AiAlertRealtimeMessage | null {
    if (typeof value !== "object" || value === null) {
        return null;
    }

    const candidate = value as Partial<AiAlertRealtimeMessage>;

    return isRealtimeAction(candidate.action) &&
        typeof candidate.occurredAt === "string" &&
        isAiAlertItem(candidate.alert)
        ? {
              action: candidate.action,
              occurredAt: candidate.occurredAt,
              alert: candidate.alert,
          }
        : null;
}
