import type { OperationsDashboardData } from "@/types/operations-dashboard";

export type OperationsStatisticsAiHealthStatus =
  | "NORMAL"
  | "WARNING"
  | "CRITICAL"
  | "WAITING_INPUT"
  | "STOPPED";

export interface OperationsStatisticsAiIngestMetrics {
  enabled: boolean;
  running: boolean;
  queueDepth: number;
  queueCapacity: number;
  acceptedFrames: number;
  droppedFrames: number;
  dropRatePct: number;
  inputFps: number;
  lastReceivedAt: string | null;
}

export interface OperationsStatisticsAiMetrics {
  running: boolean;
  modelName: string;
  device: string;
  sourceType: string;
  configuredInputFps: number;
  processedFrames: number;
  detectedFrames: number;
  totalDetections: number;
  processingFps: number;
  averageInferenceMs: number;
  p95InferenceMs: number;
  maximumInferenceMs: number;
  rollingSampleCount: number;
  rollingWindowSeconds: number;
  lastProcessedAt: string | null;
  ingest: OperationsStatisticsAiIngestMetrics | null;
  stream: {
    running: boolean;
    connectedClients: number;
    hasFrame: boolean;
  };
  health: {
    status: OperationsStatisticsAiHealthStatus;
    reasonCodes: string[];
    inputToProcessingRatio: number | null;
    queueUtilizationPct: number;
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isNonNegativeNumber(value: unknown): value is number {
  return isFiniteNumber(value) && value >= 0;
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isDashboardStatistics(value: unknown): boolean {
  return (
    isRecord(value) &&
    ["total", "ready", "active", "completed", "aborted"].every((key) =>
      isNonNegativeNumber(value[key]),
    )
  );
}

function isAiInferenceStatistics(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonNegativeNumber(value.totalEvents) &&
    isNonNegativeNumber(value.detectedEvents) &&
    isNonNegativeNumber(value.totalDetections)
  );
}

function isFlightGateStatistics(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonNegativeNumber(value.total) &&
    isNonNegativeNumber(value.allowed) &&
    isNonNegativeNumber(value.advisory) &&
    isNonNegativeNumber(value.blocked)
  );
}

export function parseOperationsStatisticsDashboard(
  value: unknown,
): OperationsDashboardData | null {
  const candidate = isRecord(value) && isRecord(value.data) ? value.data : value;

  if (
    !isRecord(candidate) ||
    typeof candidate.generatedAt !== "string" ||
    !Number.isFinite(Date.parse(candidate.generatedAt)) ||
    !isRecord(candidate.filters) ||
    !isDashboardStatistics(candidate.flightSessions) ||
    !isAiInferenceStatistics(candidate.aiInference) ||
    !isFlightGateStatistics(candidate.flightGate) ||
    !Array.isArray(candidate.recentSessions) ||
    !Array.isArray(candidate.recentAbortedSessions) ||
    !Array.isArray(candidate.recentAiAlerts) ||
    !Array.isArray(candidate.recentFlightGateDecisions)
  ) {
    return null;
  }

  const sessions = candidate.flightSessions as Record<string, number>;
  const gate = candidate.flightGate as Record<string, number>;
  if (
    sessions.ready + sessions.active + sessions.completed + sessions.aborted !==
      sessions.total ||
    gate.allowed + gate.advisory + gate.blocked !== gate.total
  ) {
    return null;
  }

  return candidate as unknown as OperationsDashboardData;
}

function isAiIngestMetrics(
  value: unknown,
): value is OperationsStatisticsAiIngestMetrics {
  return (
    isRecord(value) &&
    typeof value.enabled === "boolean" &&
    typeof value.running === "boolean" &&
    isNonNegativeNumber(value.queueDepth) &&
    isNonNegativeNumber(value.queueCapacity) &&
    isNonNegativeNumber(value.acceptedFrames) &&
    isNonNegativeNumber(value.droppedFrames) &&
    isNonNegativeNumber(value.dropRatePct) &&
    isNonNegativeNumber(value.inputFps) &&
    isNullableString(value.lastReceivedAt)
  );
}

function isAiHealthStatus(
  value: unknown,
): value is OperationsStatisticsAiHealthStatus {
  return (
    value === "NORMAL" ||
    value === "WARNING" ||
    value === "CRITICAL" ||
    value === "WAITING_INPUT" ||
    value === "STOPPED"
  );
}

export function parseOperationsStatisticsAiMetrics(
  value: unknown,
): OperationsStatisticsAiMetrics | null {
  const candidate = isRecord(value) && isRecord(value.data) ? value.data : value;
  if (!isRecord(candidate) || !isRecord(candidate.stream) || !isRecord(candidate.health)) {
    return null;
  }

  const valid =
    typeof candidate.running === "boolean" &&
    typeof candidate.modelName === "string" &&
    typeof candidate.device === "string" &&
    typeof candidate.sourceType === "string" &&
    isNonNegativeNumber(candidate.configuredInputFps) &&
    isNonNegativeNumber(candidate.processedFrames) &&
    isNonNegativeNumber(candidate.detectedFrames) &&
    isNonNegativeNumber(candidate.totalDetections) &&
    isNonNegativeNumber(candidate.processingFps) &&
    isNonNegativeNumber(candidate.averageInferenceMs) &&
    isNonNegativeNumber(candidate.p95InferenceMs) &&
    isNonNegativeNumber(candidate.maximumInferenceMs) &&
    isNonNegativeNumber(candidate.rollingSampleCount) &&
    isNonNegativeNumber(candidate.rollingWindowSeconds) &&
    isNullableString(candidate.lastProcessedAt) &&
    (candidate.ingest === null || isAiIngestMetrics(candidate.ingest)) &&
    typeof candidate.stream.running === "boolean" &&
    isNonNegativeNumber(candidate.stream.connectedClients) &&
    typeof candidate.stream.hasFrame === "boolean" &&
    isAiHealthStatus(candidate.health.status) &&
    Array.isArray(candidate.health.reasonCodes) &&
    candidate.health.reasonCodes.every((reason) => typeof reason === "string") &&
    (candidate.health.inputToProcessingRatio === null ||
      isNonNegativeNumber(candidate.health.inputToProcessingRatio)) &&
    isNonNegativeNumber(candidate.health.queueUtilizationPct);

  return valid ? (candidate as unknown as OperationsStatisticsAiMetrics) : null;
}
