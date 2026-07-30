import type {
  FlightClearanceStatus,
  MaintenanceWorkOrderStatus,
} from "@/types/maintenance-work-order";

export type MaintenanceFlightGateMode =
  | "OFF"
  | "ADVISORY"
  | "ENFORCED";

export interface MaintenanceFlightClearance {
  droneId: number;
  mode: MaintenanceFlightGateMode;
  enforced: boolean;
  flightAllowed: boolean;
  attentionRequired: boolean;
  workOrderId: number | null;
  workOrderStatus: MaintenanceWorkOrderStatus | null;
  clearanceStatus: FlightClearanceStatus | null;
  reason: string;
}

export interface MaintenanceFleetFlightClearance {
  mode: MaintenanceFlightGateMode;
  enforced: boolean;
  totalDrones: number;
  allowedDrones: number;
  attentionDrones: number;
  blockedDrones: number;
  evaluatedAt: string;
  clearances: MaintenanceFlightClearance[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isMode(value: unknown): value is MaintenanceFlightGateMode {
  return value === "OFF" || value === "ADVISORY" || value === "ENFORCED";
}

function isWorkOrderStatus(
  value: unknown,
): value is MaintenanceWorkOrderStatus {
  return (
    value === "OPEN" ||
    value === "IN_PROGRESS" ||
    value === "COMPLETED" ||
    value === "GROUNDED"
  );
}

function isClearanceStatus(value: unknown): value is FlightClearanceStatus {
  return (
    value === "PENDING_INSPECTION" ||
    value === "CLEARED" ||
    value === "GROUNDED"
  );
}

export function parseMaintenanceFlightClearance(
  value: unknown,
): MaintenanceFlightClearance | null {
  const candidate = isRecord(value) && isRecord(value.data)
    ? value.data
    : value;

  if (
    !isRecord(candidate) ||
    typeof candidate.droneId !== "number" ||
    !isMode(candidate.mode) ||
    typeof candidate.enforced !== "boolean" ||
    typeof candidate.flightAllowed !== "boolean" ||
    typeof candidate.attentionRequired !== "boolean" ||
    !(
      candidate.workOrderId === null ||
      typeof candidate.workOrderId === "number"
    ) ||
    !(
      candidate.workOrderStatus === null ||
      isWorkOrderStatus(candidate.workOrderStatus)
    ) ||
    !(
      candidate.clearanceStatus === null ||
      isClearanceStatus(candidate.clearanceStatus)
    ) ||
    typeof candidate.reason !== "string"
  ) {
    return null;
  }

  return candidate as unknown as MaintenanceFlightClearance;
}

function isNonNegativeInteger(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= 0
  );
}

export function parseMaintenanceFleetFlightClearance(
  value: unknown,
): MaintenanceFleetFlightClearance | null {
  const candidate = isRecord(value) && isRecord(value.data)
    ? value.data
    : value;

  if (
    !isRecord(candidate) ||
    !isMode(candidate.mode) ||
    typeof candidate.enforced !== "boolean" ||
    !isNonNegativeInteger(candidate.totalDrones) ||
    !isNonNegativeInteger(candidate.allowedDrones) ||
    !isNonNegativeInteger(candidate.attentionDrones) ||
    !isNonNegativeInteger(candidate.blockedDrones) ||
    typeof candidate.evaluatedAt !== "string" ||
    !Number.isFinite(Date.parse(candidate.evaluatedAt)) ||
    !Array.isArray(candidate.clearances)
  ) {
    return null;
  }

  const clearances = candidate.clearances.map(
    parseMaintenanceFlightClearance,
  );
  if (
    clearances.some((clearance) => clearance === null) ||
    clearances.length !== candidate.totalDrones ||
    candidate.allowedDrones + candidate.blockedDrones !==
      candidate.totalDrones
  ) {
    return null;
  }

  return {
    mode: candidate.mode,
    enforced: candidate.enforced,
    totalDrones: candidate.totalDrones,
    allowedDrones: candidate.allowedDrones,
    attentionDrones: candidate.attentionDrones,
    blockedDrones: candidate.blockedDrones,
    evaluatedAt: candidate.evaluatedAt,
    clearances: clearances as MaintenanceFlightClearance[],
  };
}
