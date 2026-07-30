export interface MaintenanceSlaAutomationStatus {
  automationEnabled: boolean;
  openSlaMinutes: number;
  inProgressSlaMinutes: number;
  dueSoonMinutes: number;
  initialDelayMs: number;
  scanDelayMs: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isPositiveInteger(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value > 0
  );
}

export function parseMaintenanceSlaAutomationStatus(
  value: unknown,
): MaintenanceSlaAutomationStatus | null {
  const candidate = isRecord(value) && isRecord(value.data)
    ? value.data
    : value;

  if (
    !isRecord(candidate) ||
    typeof candidate.automationEnabled !== "boolean" ||
    !isPositiveInteger(candidate.openSlaMinutes) ||
    !isPositiveInteger(candidate.inProgressSlaMinutes) ||
    !isPositiveInteger(candidate.dueSoonMinutes) ||
    !isPositiveInteger(candidate.initialDelayMs) ||
    !isPositiveInteger(candidate.scanDelayMs) ||
    candidate.dueSoonMinutes > candidate.openSlaMinutes ||
    candidate.dueSoonMinutes > candidate.inProgressSlaMinutes
  ) {
    return null;
  }

  return candidate as unknown as MaintenanceSlaAutomationStatus;
}
