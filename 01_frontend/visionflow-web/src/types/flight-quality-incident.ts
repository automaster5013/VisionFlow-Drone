import type { FleetReliabilityStatus } from "@/types/fleet-reliability";
import {
  isIncidentItem,
  type IncidentItem,
} from "@/types/incident";

export type FlightQualityIncidentSyncAction =
  | "CREATED"
  | "UPDATED"
  | "DEDUPLICATED"
  | "REOPENED"
  | "RESOLVED"
  | "SKIPPED_STABLE";

export interface FlightQualityIncidentSyncItem {
  droneId: number;
  reliabilityStatus: FleetReliabilityStatus;
  action: FlightQualityIncidentSyncAction;
  incident: IncidentItem | null;
}

export interface FlightQualityIncidentSyncResponse {
  synchronizedAt: string;
  limitPerDrone: number;
  evaluatedDroneCount: number;
  createdCount: number;
  updatedCount: number;
  deduplicatedCount: number;
  reopenedCount: number;
  resolvedCount: number;
  skippedCount: number;
  items: FlightQualityIncidentSyncItem[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isCount(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) >= 0;
}

function isReliabilityStatus(
  value: unknown,
): value is FleetReliabilityStatus {
  return value === "STABLE" || value === "WATCH" || value === "CHECK";
}

function isAction(
  value: unknown,
): value is FlightQualityIncidentSyncAction {
  return (
    value === "CREATED" ||
    value === "UPDATED" ||
    value === "DEDUPLICATED" ||
    value === "REOPENED" ||
    value === "RESOLVED" ||
    value === "SKIPPED_STABLE"
  );
}

function isItem(value: unknown): value is FlightQualityIncidentSyncItem {
  return (
    isRecord(value) &&
    isCount(value.droneId) &&
    Number(value.droneId) > 0 &&
    isReliabilityStatus(value.reliabilityStatus) &&
    isAction(value.action) &&
    (value.incident === null || isIncidentItem(value.incident))
  );
}

export function parseFlightQualityIncidentSyncResponse(
  value: unknown,
): FlightQualityIncidentSyncResponse | null {
  const candidate =
    isRecord(value) && "data" in value ? value.data : value;

  if (
    !isRecord(candidate) ||
    typeof candidate.synchronizedAt !== "string" ||
    !isCount(candidate.limitPerDrone) ||
    !isCount(candidate.evaluatedDroneCount) ||
    !isCount(candidate.createdCount) ||
    !isCount(candidate.updatedCount) ||
    !isCount(candidate.deduplicatedCount) ||
    !isCount(candidate.reopenedCount) ||
    !isCount(candidate.resolvedCount) ||
    !isCount(candidate.skippedCount) ||
    !Array.isArray(candidate.items) ||
    !candidate.items.every(isItem)
  ) {
    return null;
  }

  return candidate as unknown as FlightQualityIncidentSyncResponse;
}
