import type {
  IncidentPriority,
  IncidentStatus,
} from "@/types/incident";
import type {
  MaintenanceSlaStatus,
} from "@/types/maintenance-priority";
import type {
  FlightClearanceStatus,
  MaintenanceWorkOrderStatus,
} from "@/types/maintenance-work-order";

export type MaintenanceSlaResponseStatus =
  | "MONITORING"
  | "ESCALATION_PENDING"
  | "ASSIGNMENT_REQUIRED"
  | "IN_RESPONSE"
  | "COMPLETED";

export type MaintenanceSlaClosureStatus =
  | "RESPONSE_ACTIVE"
  | "WORK_ORDER_PENDING"
  | "RETURN_TO_SERVICE_CONFIRMED"
  | "GROUNDED_CONFIRMED"
  | "REVIEW_REQUIRED";

export interface MaintenanceSlaIncidentTrackingItem {
  workOrderId: number;
  incidentId: number;
  droneId: number;
  workOrderStatus: MaintenanceWorkOrderStatus;
  flightClearanceStatus: FlightClearanceStatus;
  incidentStatus: IncidentStatus | null;
  incidentPriority: IncidentPriority | null;
  incidentTitle: string | null;
  incidentAssignee: string | null;
  slaStatus: MaintenanceSlaStatus;
  slaDueAt: string | null;
  slaOverdueMinutes: number | null;
  escalated: boolean;
  escalatedAt: string | null;
  escalationActor: string | null;
  escalationNote: string | null;
  responseStatus: MaintenanceSlaResponseStatus;
  recommendedAction: string;
  closureStatus: MaintenanceSlaClosureStatus;
  closureRecommendedAction: string;
}

export interface MaintenanceSlaIncidentTracking {
  evaluatedAt: string;
  windowDays: number;
  totalWorkOrders: number;
  connectedIncidents: number;
  overdueWorkOrders: number;
  escalatedIncidents: number;
  monitoringWorkOrders: number;
  escalationPendingIncidents: number;
  assignmentRequiredIncidents: number;
  inResponseIncidents: number;
  completedResponses: number;
  pendingWorkOrderClosures: number;
  returnToServiceConfirmed: number;
  groundedClosures: number;
  closureConsistencyAlerts: number;
  items: MaintenanceSlaIncidentTrackingItem[];
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

function isPositiveInteger(value: unknown): value is number {
  return isNonNegativeInteger(value) && value > 0;
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
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

function isIncidentStatus(value: unknown): value is IncidentStatus {
  return (
    value === "OPEN" ||
    value === "IN_PROGRESS" ||
    value === "RESOLVED" ||
    value === "CLOSED"
  );
}

function isIncidentPriority(value: unknown): value is IncidentPriority {
  return (
    value === "LOW" ||
    value === "MEDIUM" ||
    value === "HIGH" ||
    value === "CRITICAL"
  );
}

function isSlaStatus(value: unknown): value is MaintenanceSlaStatus {
  return (
    value === "ON_TRACK" ||
    value === "DUE_SOON" ||
    value === "OVERDUE" ||
    value === "NOT_APPLICABLE"
  );
}

function isResponseStatus(
  value: unknown,
): value is MaintenanceSlaResponseStatus {
  return (
    value === "MONITORING" ||
    value === "ESCALATION_PENDING" ||
    value === "ASSIGNMENT_REQUIRED" ||
    value === "IN_RESPONSE" ||
    value === "COMPLETED"
  );
}

function isFlightClearanceStatus(
  value: unknown,
): value is FlightClearanceStatus {
  return (
    value === "PENDING_INSPECTION" ||
    value === "CLEARED" ||
    value === "GROUNDED"
  );
}

function isClosureStatus(
  value: unknown,
): value is MaintenanceSlaClosureStatus {
  return (
    value === "RESPONSE_ACTIVE" ||
    value === "WORK_ORDER_PENDING" ||
    value === "RETURN_TO_SERVICE_CONFIRMED" ||
    value === "GROUNDED_CONFIRMED" ||
    value === "REVIEW_REQUIRED"
  );
}

function isTrackingItem(
  value: unknown,
): value is MaintenanceSlaIncidentTrackingItem {
  return (
    isRecord(value) &&
    isPositiveInteger(value.workOrderId) &&
    isPositiveInteger(value.incidentId) &&
    isPositiveInteger(value.droneId) &&
    isWorkOrderStatus(value.workOrderStatus) &&
    isFlightClearanceStatus(value.flightClearanceStatus) &&
    (
      value.incidentStatus === null ||
      isIncidentStatus(value.incidentStatus)
    ) &&
    (
      value.incidentPriority === null ||
      isIncidentPriority(value.incidentPriority)
    ) &&
    isNullableString(value.incidentTitle) &&
    isNullableString(value.incidentAssignee) &&
    isSlaStatus(value.slaStatus) &&
    isNullableDateTime(value.slaDueAt) &&
    (
      value.slaOverdueMinutes === null ||
      isNonNegativeInteger(value.slaOverdueMinutes)
    ) &&
    typeof value.escalated === "boolean" &&
    isNullableDateTime(value.escalatedAt) &&
    isNullableString(value.escalationActor) &&
    isNullableString(value.escalationNote) &&
    (
      value.escalated
        ? value.escalatedAt !== null &&
          value.escalationActor !== null
        : value.escalatedAt === null &&
          value.escalationActor === null &&
          value.escalationNote === null
    ) &&
    isResponseStatus(value.responseStatus) &&
    typeof value.recommendedAction === "string" &&
    value.recommendedAction.length > 0 &&
    isClosureStatus(value.closureStatus) &&
    typeof value.closureRecommendedAction === "string" &&
    value.closureRecommendedAction.length > 0
  );
}

export function parseMaintenanceSlaIncidentTracking(
  value: unknown,
): MaintenanceSlaIncidentTracking | null {
  const candidate = isRecord(value) && isRecord(value.data)
    ? value.data
    : value;

  if (
    !isRecord(candidate) ||
    typeof candidate.evaluatedAt !== "string" ||
    !Number.isFinite(Date.parse(candidate.evaluatedAt)) ||
    !isPositiveInteger(candidate.windowDays) ||
    !isNonNegativeInteger(candidate.totalWorkOrders) ||
    !isNonNegativeInteger(candidate.connectedIncidents) ||
    !isNonNegativeInteger(candidate.overdueWorkOrders) ||
    !isNonNegativeInteger(candidate.escalatedIncidents) ||
    !isNonNegativeInteger(candidate.monitoringWorkOrders) ||
    !isNonNegativeInteger(candidate.escalationPendingIncidents) ||
    !isNonNegativeInteger(candidate.assignmentRequiredIncidents) ||
    !isNonNegativeInteger(candidate.inResponseIncidents) ||
    !isNonNegativeInteger(candidate.completedResponses) ||
    !isNonNegativeInteger(candidate.pendingWorkOrderClosures) ||
    !isNonNegativeInteger(candidate.returnToServiceConfirmed) ||
    !isNonNegativeInteger(candidate.groundedClosures) ||
    !isNonNegativeInteger(candidate.closureConsistencyAlerts) ||
    !Array.isArray(candidate.items) ||
    !candidate.items.every(isTrackingItem)
  ) {
    return null;
  }

  if (
    candidate.totalWorkOrders !== candidate.items.length ||
    candidate.connectedIncidents !==
      candidate.items.filter(
        (item) => item.incidentStatus !== null,
      ).length ||
    candidate.overdueWorkOrders !==
      candidate.items.filter(
        (item) => item.slaStatus === "OVERDUE",
      ).length ||
    candidate.escalatedIncidents !==
      candidate.items.filter((item) => item.escalated).length ||
    candidate.monitoringWorkOrders !==
      countResponseStatus(candidate.items, "MONITORING") ||
    candidate.escalationPendingIncidents !==
      countResponseStatus(candidate.items, "ESCALATION_PENDING") ||
    candidate.assignmentRequiredIncidents !==
      countResponseStatus(candidate.items, "ASSIGNMENT_REQUIRED") ||
    candidate.inResponseIncidents !==
      countResponseStatus(candidate.items, "IN_RESPONSE") ||
    candidate.completedResponses !==
      countResponseStatus(candidate.items, "COMPLETED") ||
    candidate.pendingWorkOrderClosures !==
      countClosureStatus(candidate.items, "WORK_ORDER_PENDING") ||
    candidate.returnToServiceConfirmed !==
      countClosureStatus(
        candidate.items,
        "RETURN_TO_SERVICE_CONFIRMED",
      ) ||
    candidate.groundedClosures !==
      countClosureStatus(candidate.items, "GROUNDED_CONFIRMED") ||
    candidate.closureConsistencyAlerts !==
      countClosureStatus(candidate.items, "REVIEW_REQUIRED") ||
    candidate.monitoringWorkOrders +
      candidate.escalationPendingIncidents +
      candidate.assignmentRequiredIncidents +
      candidate.inResponseIncidents +
      candidate.completedResponses !==
      candidate.totalWorkOrders
  ) {
    return null;
  }

  return candidate as unknown as MaintenanceSlaIncidentTracking;
}

function countResponseStatus(
  items: MaintenanceSlaIncidentTrackingItem[],
  status: MaintenanceSlaResponseStatus,
): number {
  return items.filter((item) => item.responseStatus === status).length;
}

function countClosureStatus(
  items: MaintenanceSlaIncidentTrackingItem[],
  status: MaintenanceSlaClosureStatus,
): number {
  return items.filter((item) => item.closureStatus === status).length;
}
