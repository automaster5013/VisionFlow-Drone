import type {
  MaintenanceFlightGateMode,
} from "@/types/maintenance-flight-clearance";

export interface MaintenanceMetrics {
  windowDays: number;
  windowStartedAt: string;
  generatedAt: string;
  totalWorkOrders: number;
  openWorkOrders: number;
  inProgressWorkOrders: number;
  completedWorkOrders: number;
  groundedWorkOrders: number;
  resolvedWorkOrders: number;
  resolutionRatePercent: number;
  averageStartDelayMinutes: number | null;
  averageResolutionMinutes: number | null;
  gateMode: MaintenanceFlightGateMode;
  gateEnforced: boolean;
  totalDrones: number;
  allowedDrones: number;
  attentionDrones: number;
  blockedDrones: number;
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

function isNullableNonNegativeInteger(
  value: unknown,
): value is number | null {
  return value === null || isNonNegativeInteger(value);
}

function isMode(value: unknown): value is MaintenanceFlightGateMode {
  return value === "OFF" || value === "ADVISORY" || value === "ENFORCED";
}

function isDateTime(value: unknown): value is string {
  return (
    typeof value === "string" &&
    Number.isFinite(Date.parse(value))
  );
}

export function parseMaintenanceMetrics(
  value: unknown,
): MaintenanceMetrics | null {
  const candidate = isRecord(value) && isRecord(value.data)
    ? value.data
    : value;

  if (
    !isRecord(candidate) ||
    !isNonNegativeInteger(candidate.windowDays) ||
    candidate.windowDays < 1 ||
    candidate.windowDays > 365 ||
    !isDateTime(candidate.windowStartedAt) ||
    !isDateTime(candidate.generatedAt) ||
    !isNonNegativeInteger(candidate.totalWorkOrders) ||
    !isNonNegativeInteger(candidate.openWorkOrders) ||
    !isNonNegativeInteger(candidate.inProgressWorkOrders) ||
    !isNonNegativeInteger(candidate.completedWorkOrders) ||
    !isNonNegativeInteger(candidate.groundedWorkOrders) ||
    !isNonNegativeInteger(candidate.resolvedWorkOrders) ||
    typeof candidate.resolutionRatePercent !== "number" ||
    !Number.isFinite(candidate.resolutionRatePercent) ||
    candidate.resolutionRatePercent < 0 ||
    candidate.resolutionRatePercent > 100 ||
    !isNullableNonNegativeInteger(candidate.averageStartDelayMinutes) ||
    !isNullableNonNegativeInteger(candidate.averageResolutionMinutes) ||
    !isMode(candidate.gateMode) ||
    typeof candidate.gateEnforced !== "boolean" ||
    !isNonNegativeInteger(candidate.totalDrones) ||
    !isNonNegativeInteger(candidate.allowedDrones) ||
    !isNonNegativeInteger(candidate.attentionDrones) ||
    !isNonNegativeInteger(candidate.blockedDrones)
  ) {
    return null;
  }

  if (
    candidate.openWorkOrders +
      candidate.inProgressWorkOrders +
      candidate.completedWorkOrders +
      candidate.groundedWorkOrders !==
      candidate.totalWorkOrders ||
    candidate.completedWorkOrders + candidate.groundedWorkOrders !==
      candidate.resolvedWorkOrders ||
    candidate.allowedDrones + candidate.blockedDrones !==
      candidate.totalDrones ||
    candidate.attentionDrones > candidate.totalDrones ||
    candidate.gateEnforced !== (candidate.gateMode === "ENFORCED")
  ) {
    return null;
  }

  return candidate as unknown as MaintenanceMetrics;
}
