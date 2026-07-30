import type {
  MaintenanceFlightGateMode,
} from "@/types/maintenance-flight-clearance";
import type {
  FlightClearanceStatus,
  MaintenanceWorkOrderStatus,
} from "@/types/maintenance-work-order";

export type MaintenancePriorityLevel =
  | "CRITICAL"
  | "HIGH"
  | "MEDIUM"
  | "LOW";

export type MaintenanceSlaStatus =
  | "ON_TRACK"
  | "DUE_SOON"
  | "OVERDUE"
  | "NOT_APPLICABLE";

export interface MaintenancePriorityItem {
  droneId: number;
  priority: MaintenancePriorityLevel;
  riskScore: number;
  flightAllowed: boolean;
  attentionRequired: boolean;
  workOrderId: number | null;
  workOrderStatus: MaintenanceWorkOrderStatus | null;
  clearanceStatus: FlightClearanceStatus | null;
  openedAt: string | null;
  waitingMinutes: number | null;
  slaStatus: MaintenanceSlaStatus;
  slaDueAt: string | null;
  slaRemainingMinutes: number | null;
  slaOverdueMinutes: number | null;
  recommendedAction: string;
  reason: string;
}

export interface MaintenancePriorityQueue {
  mode: MaintenanceFlightGateMode;
  enforced: boolean;
  evaluatedAt: string;
  totalDrones: number;
  urgentDrones: number;
  attentionDrones: number;
  normalDrones: number;
  overdueDrones: number;
  dueSoonDrones: number;
  priorities: MaintenancePriorityItem[];
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

function isPriority(value: unknown): value is MaintenancePriorityLevel {
  return (
    value === "CRITICAL" ||
    value === "HIGH" ||
    value === "MEDIUM" ||
    value === "LOW"
  );
}

function isMode(value: unknown): value is MaintenanceFlightGateMode {
  return value === "OFF" || value === "ADVISORY" || value === "ENFORCED";
}

function isSlaStatus(value: unknown): value is MaintenanceSlaStatus {
  return (
    value === "ON_TRACK" ||
    value === "DUE_SOON" ||
    value === "OVERDUE" ||
    value === "NOT_APPLICABLE"
  );
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

function isNullableDateTime(value: unknown): value is string | null {
  return (
    value === null ||
    (
      typeof value === "string" &&
      Number.isFinite(Date.parse(value))
    )
  );
}

function isPriorityItem(value: unknown): value is MaintenancePriorityItem {
  return (
    isRecord(value) &&
    isNonNegativeInteger(value.droneId) &&
    value.droneId > 0 &&
    isPriority(value.priority) &&
    isNonNegativeInteger(value.riskScore) &&
    value.riskScore <= 100 &&
    typeof value.flightAllowed === "boolean" &&
    typeof value.attentionRequired === "boolean" &&
    isNullableNonNegativeInteger(value.workOrderId) &&
    (
      value.workOrderStatus === null ||
      isWorkOrderStatus(value.workOrderStatus)
    ) &&
    (
      value.clearanceStatus === null ||
      isClearanceStatus(value.clearanceStatus)
    ) &&
    isNullableDateTime(value.openedAt) &&
    isNullableNonNegativeInteger(value.waitingMinutes) &&
    isSlaStatus(value.slaStatus) &&
    isNullableDateTime(value.slaDueAt) &&
    isNullableNonNegativeInteger(value.slaRemainingMinutes) &&
    isNullableNonNegativeInteger(value.slaOverdueMinutes) &&
    (
      value.slaStatus === "NOT_APPLICABLE"
        ? value.slaDueAt === null &&
          value.slaRemainingMinutes === null &&
          value.slaOverdueMinutes === null
        : value.slaDueAt !== null &&
          value.slaRemainingMinutes !== null &&
          value.slaOverdueMinutes !== null
    ) &&
    typeof value.recommendedAction === "string" &&
    typeof value.reason === "string"
  );
}

export function parseMaintenancePriorityQueue(
  value: unknown,
): MaintenancePriorityQueue | null {
  const candidate = isRecord(value) && isRecord(value.data)
    ? value.data
    : value;

  if (
    !isRecord(candidate) ||
    !isMode(candidate.mode) ||
    typeof candidate.enforced !== "boolean" ||
    typeof candidate.evaluatedAt !== "string" ||
    !Number.isFinite(Date.parse(candidate.evaluatedAt)) ||
    !isNonNegativeInteger(candidate.totalDrones) ||
    !isNonNegativeInteger(candidate.urgentDrones) ||
    !isNonNegativeInteger(candidate.attentionDrones) ||
    !isNonNegativeInteger(candidate.normalDrones) ||
    !isNonNegativeInteger(candidate.overdueDrones) ||
    !isNonNegativeInteger(candidate.dueSoonDrones) ||
    !Array.isArray(candidate.priorities) ||
    !candidate.priorities.every(isPriorityItem)
  ) {
    return null;
  }

  if (
    candidate.priorities.length !== candidate.totalDrones ||
    candidate.urgentDrones +
      candidate.attentionDrones +
      candidate.normalDrones !==
      candidate.totalDrones ||
    candidate.overdueDrones > candidate.totalDrones ||
    candidate.dueSoonDrones > candidate.totalDrones ||
    candidate.overdueDrones !==
      candidate.priorities.filter(
        (item) => item.slaStatus === "OVERDUE",
      ).length ||
    candidate.dueSoonDrones !==
      candidate.priorities.filter(
        (item) => item.slaStatus === "DUE_SOON",
      ).length ||
    candidate.enforced !== (candidate.mode === "ENFORCED")
  ) {
    return null;
  }

  return candidate as unknown as MaintenancePriorityQueue;
}
