import {
  isPersistedFlightQualityAssessment,
  type PersistedFlightQualityAssessment,
} from "@/types/flight-quality-assessment";

export type FleetReliabilityStatus = "STABLE" | "WATCH" | "CHECK";

export interface FleetReliabilityTrendPoint {
  sessionId: string;
  sessionName: string;
  sessionStatus: "COMPLETED" | "ABORTED";
  startedAt: string;
  endedAt: string;
  durationSeconds: number;
  quality: PersistedFlightQualityAssessment;
}

export interface FleetDroneReliability {
  droneId: number;
  droneCode: string | null;
  droneName: string | null;
  modelName: string | null;
  status: FleetReliabilityStatus;
  assessmentCount: number;
  averageScore: number;
  minimumScore: number;
  latestScore: number;
  previousScore: number | null;
  completedCount: number;
  abortedCount: number;
  totalDurationSeconds: number;
  criticalCount: number;
  warningCount: number;
  latestAssessment: PersistedFlightQualityAssessment;
  trend: FleetReliabilityTrendPoint[];
}

export interface FleetReliabilityResponse {
  generatedAt: string;
  ruleVersion: string;
  limitPerDrone: number;
  droneCount: number;
  assessmentCount: number;
  fleetAverageScore: number;
  attentionDroneCount: number;
  backfillCandidateDroneIds: number[];
  drones: FleetDroneReliability[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isNonNegativeNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isReliabilityStatus(
  value: unknown,
): value is FleetReliabilityStatus {
  return value === "STABLE" || value === "WATCH" || value === "CHECK";
}

function isTrendPoint(value: unknown): value is FleetReliabilityTrendPoint {
  return (
    isRecord(value) &&
    typeof value.sessionId === "string" &&
    typeof value.sessionName === "string" &&
    (value.sessionStatus === "COMPLETED" ||
      value.sessionStatus === "ABORTED") &&
    typeof value.startedAt === "string" &&
    typeof value.endedAt === "string" &&
    isNonNegativeNumber(value.durationSeconds) &&
    isPersistedFlightQualityAssessment(value.quality)
  );
}

function isDroneReliability(
  value: unknown,
): value is FleetDroneReliability {
  return (
    isRecord(value) &&
    isNonNegativeNumber(value.droneId) &&
    isNullableString(value.droneCode) &&
    isNullableString(value.droneName) &&
    isNullableString(value.modelName) &&
    isReliabilityStatus(value.status) &&
    isNonNegativeNumber(value.assessmentCount) &&
    isNonNegativeNumber(value.averageScore) &&
    isNonNegativeNumber(value.minimumScore) &&
    isNonNegativeNumber(value.latestScore) &&
    (value.previousScore === null ||
      isNonNegativeNumber(value.previousScore)) &&
    isNonNegativeNumber(value.completedCount) &&
    isNonNegativeNumber(value.abortedCount) &&
    isNonNegativeNumber(value.totalDurationSeconds) &&
    isNonNegativeNumber(value.criticalCount) &&
    isNonNegativeNumber(value.warningCount) &&
    isPersistedFlightQualityAssessment(value.latestAssessment) &&
    Array.isArray(value.trend) &&
    value.trend.every(isTrendPoint)
  );
}

export function extractFleetReliabilityResponse(
  value: unknown,
): FleetReliabilityResponse | null {
  const candidate = isRecord(value) && isRecord(value.data) ? value.data : value;

  if (
    !isRecord(candidate) ||
    typeof candidate.generatedAt !== "string" ||
    typeof candidate.ruleVersion !== "string" ||
    !isNonNegativeNumber(candidate.limitPerDrone) ||
    !isNonNegativeNumber(candidate.droneCount) ||
    !isNonNegativeNumber(candidate.assessmentCount) ||
    !isNonNegativeNumber(candidate.fleetAverageScore) ||
    !isNonNegativeNumber(candidate.attentionDroneCount) ||
    !Array.isArray(candidate.backfillCandidateDroneIds) ||
    !candidate.backfillCandidateDroneIds.every(isNonNegativeNumber) ||
    !Array.isArray(candidate.drones) ||
    !candidate.drones.every(isDroneReliability)
  ) {
    return null;
  }

  return {
    generatedAt: candidate.generatedAt,
    ruleVersion: candidate.ruleVersion,
    limitPerDrone: candidate.limitPerDrone,
    droneCount: candidate.droneCount,
    assessmentCount: candidate.assessmentCount,
    fleetAverageScore: candidate.fleetAverageScore,
    attentionDroneCount: candidate.attentionDroneCount,
    backfillCandidateDroneIds: candidate.backfillCandidateDroneIds,
    drones: candidate.drones,
  };
}
