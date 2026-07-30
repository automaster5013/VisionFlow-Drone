import type { FlightSessionSummaryStatus } from "@/types/flight-session-replay";

export type PersistedFlightQualityGrade =
  | "EXCELLENT"
  | "GOOD"
  | "CAUTION"
  | "RISK";

export type PersistedFlightRiskSeverity = "WARNING" | "CRITICAL";

export interface PersistedFlightQualityRisk {
  severity: PersistedFlightRiskSeverity;
  title: string;
  detail: string;
}

export interface PersistedFlightQualityMetrics {
  telemetryCount: number;
  validCoordinateCount: number;
  coordinateCoveragePercent: number;
  batteryCoveragePercent: number;
  maxTelemetryGapSeconds: number | null;
  unrealisticJumpCount: number;
  altitudeSpikeCount: number;
  batteryIncreaseCount: number;
  minimumBatteryLevel: number | null;
  aiEventCount: number;
  detectedEventCount: number;
  averageInferenceMs: number | null;
  snapshotCoveragePercent: number;
}

export interface PersistedFlightQualityAssessment {
  id: number;
  droneId: number;
  sessionId: string;
  sessionStatus: Exclude<FlightSessionSummaryStatus, "LEGACY">;
  ruleVersion: string;
  score: number;
  grade: PersistedFlightQualityGrade;
  dataScore: number;
  flightScore: number;
  aiScore: number;
  warningCount: number;
  criticalCount: number;
  primaryRisk: PersistedFlightQualityRisk | null;
  metrics: PersistedFlightQualityMetrics;
  evaluatedAt: string;
}

export interface PersistedFlightQualityBackfillFailure {
  sessionId: string;
  message: string;
}

export interface PersistedFlightQualityBackfillResponse {
  droneId: number;
  ruleVersion: string;
  force: boolean;
  candidateCount: number;
  evaluatedCount: number;
  skippedCount: number;
  failedCount: number;
  failures: PersistedFlightQualityBackfillFailure[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isNumberOrNull(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function isNonNegativeNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function isSessionStatus(
  value: unknown,
): value is PersistedFlightQualityAssessment["sessionStatus"] {
  return (
    value === "READY" ||
    value === "ACTIVE" ||
    value === "COMPLETED" ||
    value === "ABORTED"
  );
}

function isGrade(value: unknown): value is PersistedFlightQualityGrade {
  return (
    value === "EXCELLENT" ||
    value === "GOOD" ||
    value === "CAUTION" ||
    value === "RISK"
  );
}

function isRisk(
  value: unknown,
): value is PersistedFlightQualityRisk | null {
  return (
    value === null ||
    (isRecord(value) &&
      (value.severity === "WARNING" || value.severity === "CRITICAL") &&
      typeof value.title === "string" &&
      typeof value.detail === "string")
  );
}

function isMetrics(value: unknown): value is PersistedFlightQualityMetrics {
  return (
    isRecord(value) &&
    isNonNegativeNumber(value.telemetryCount) &&
    isNonNegativeNumber(value.validCoordinateCount) &&
    isNonNegativeNumber(value.coordinateCoveragePercent) &&
    isNonNegativeNumber(value.batteryCoveragePercent) &&
    isNumberOrNull(value.maxTelemetryGapSeconds) &&
    isNonNegativeNumber(value.unrealisticJumpCount) &&
    isNonNegativeNumber(value.altitudeSpikeCount) &&
    isNonNegativeNumber(value.batteryIncreaseCount) &&
    isNumberOrNull(value.minimumBatteryLevel) &&
    isNonNegativeNumber(value.aiEventCount) &&
    isNonNegativeNumber(value.detectedEventCount) &&
    isNumberOrNull(value.averageInferenceMs) &&
    isNonNegativeNumber(value.snapshotCoveragePercent)
  );
}

export function isPersistedFlightQualityAssessment(
  value: unknown,
): value is PersistedFlightQualityAssessment {
  return (
    isRecord(value) &&
    isNonNegativeNumber(value.id) &&
    isNonNegativeNumber(value.droneId) &&
    typeof value.sessionId === "string" &&
    isSessionStatus(value.sessionStatus) &&
    typeof value.ruleVersion === "string" &&
    isNonNegativeNumber(value.score) &&
    isGrade(value.grade) &&
    isNonNegativeNumber(value.dataScore) &&
    isNonNegativeNumber(value.flightScore) &&
    isNonNegativeNumber(value.aiScore) &&
    isNonNegativeNumber(value.warningCount) &&
    isNonNegativeNumber(value.criticalCount) &&
    isRisk(value.primaryRisk) &&
    isMetrics(value.metrics) &&
    typeof value.evaluatedAt === "string"
  );
}

export function extractPersistedFlightQualityAssessments(
  value: unknown,
): PersistedFlightQualityAssessment[] | null {
  const candidate =
    isRecord(value) && Array.isArray(value.data) ? value.data : value;

  return Array.isArray(candidate) &&
    candidate.every(isPersistedFlightQualityAssessment)
    ? candidate
    : null;
}

export function isPersistedFlightQualityBackfillResponse(
  value: unknown,
): value is PersistedFlightQualityBackfillResponse {
  return (
    isRecord(value) &&
    isNonNegativeNumber(value.droneId) &&
    typeof value.ruleVersion === "string" &&
    typeof value.force === "boolean" &&
    isNonNegativeNumber(value.candidateCount) &&
    isNonNegativeNumber(value.evaluatedCount) &&
    isNonNegativeNumber(value.skippedCount) &&
    isNonNegativeNumber(value.failedCount) &&
    Array.isArray(value.failures) &&
    value.failures.every(
      (failure) =>
        isRecord(failure) &&
        typeof failure.sessionId === "string" &&
        typeof failure.message === "string",
    )
  );
}
