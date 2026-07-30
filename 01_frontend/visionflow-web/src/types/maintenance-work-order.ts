export type MaintenanceWorkOrderStatus =
  | "OPEN"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "GROUNDED";

export type FlightClearanceStatus =
  | "PENDING_INSPECTION"
  | "CLEARED"
  | "GROUNDED";

export type MaintenanceCompletionDecision =
  | "RETURN_TO_SERVICE"
  | "KEEP_GROUNDED";

export type MaintenanceWorkOrderActionType =
  | "CREATED"
  | "RISK_SYNCHRONIZED"
  | "REOPENED"
  | "INSPECTION_STARTED"
  | "RETURNED_TO_SERVICE"
  | "GROUNDED";

export interface MaintenanceWorkOrder {
  id: number;
  incidentId: number;
  droneId: number;
  sessionId: string | null;
  sourceAssessmentId: number | null;
  status: MaintenanceWorkOrderStatus;
  clearanceStatus: FlightClearanceStatus;
  assignee: string | null;
  finding: string | null;
  resolutionNote: string | null;
  openedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  clearedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface MaintenanceWorkOrderHistory {
  id: number;
  actionType: MaintenanceWorkOrderActionType;
  previousStatus: MaintenanceWorkOrderStatus | null;
  newStatus: MaintenanceWorkOrderStatus;
  actor: string;
  note: string | null;
  createdAt: string;
}

export interface MaintenanceWorkOrderDetail {
  workOrder: MaintenanceWorkOrder;
  history: MaintenanceWorkOrderHistory[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function isStatus(value: unknown): value is MaintenanceWorkOrderStatus {
  return (
    value === "OPEN" ||
    value === "IN_PROGRESS" ||
    value === "COMPLETED" ||
    value === "GROUNDED"
  );
}

function isClearance(value: unknown): value is FlightClearanceStatus {
  return (
    value === "PENDING_INSPECTION" ||
    value === "CLEARED" ||
    value === "GROUNDED"
  );
}

function isActionType(
  value: unknown,
): value is MaintenanceWorkOrderActionType {
  return (
    value === "CREATED" ||
    value === "RISK_SYNCHRONIZED" ||
    value === "REOPENED" ||
    value === "INSPECTION_STARTED" ||
    value === "RETURNED_TO_SERVICE" ||
    value === "GROUNDED"
  );
}

export function isMaintenanceWorkOrder(
  value: unknown,
): value is MaintenanceWorkOrder {
  return (
    isRecord(value) &&
    typeof value.id === "number" &&
    typeof value.incidentId === "number" &&
    typeof value.droneId === "number" &&
    isNullableString(value.sessionId) &&
    isNullableNumber(value.sourceAssessmentId) &&
    isStatus(value.status) &&
    isClearance(value.clearanceStatus) &&
    isNullableString(value.assignee) &&
    isNullableString(value.finding) &&
    isNullableString(value.resolutionNote) &&
    typeof value.openedAt === "string" &&
    isNullableString(value.startedAt) &&
    isNullableString(value.completedAt) &&
    isNullableString(value.clearedAt) &&
    typeof value.createdAt === "string" &&
    typeof value.updatedAt === "string"
  );
}

export function parseMaintenanceWorkOrders(
  value: unknown,
): MaintenanceWorkOrder[] | null {
  const candidate = isRecord(value) && "data" in value ? value.data : value;

  return Array.isArray(candidate) && candidate.every(isMaintenanceWorkOrder)
    ? candidate
    : null;
}

function isMaintenanceWorkOrderHistory(
  value: unknown,
): value is MaintenanceWorkOrderHistory {
  return (
    isRecord(value) &&
    typeof value.id === "number" &&
    isActionType(value.actionType) &&
    (value.previousStatus === null || isStatus(value.previousStatus)) &&
    isStatus(value.newStatus) &&
    typeof value.actor === "string" &&
    isNullableString(value.note) &&
    typeof value.createdAt === "string"
  );
}

export function parseMaintenanceWorkOrderDetail(
  value: unknown,
): MaintenanceWorkOrderDetail | null {
  const candidate = isRecord(value) && "data" in value ? value.data : value;

  if (
    !isRecord(candidate) ||
    !isMaintenanceWorkOrder(candidate.workOrder) ||
    !Array.isArray(candidate.history) ||
    !candidate.history.every(isMaintenanceWorkOrderHistory)
  ) {
    return null;
  }

  return {
    workOrder: candidate.workOrder,
    history: candidate.history,
  };
}
