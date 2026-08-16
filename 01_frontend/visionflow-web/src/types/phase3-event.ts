export type Phase3SourceType =
  | "SMARTPHONE_LIVE"
  | "DUMMY_VIDEO"
  | "DJI_LIVE";

export type Phase3DepthBucket = "NEAR" | "MID" | "FAR" | "UNKNOWN";

export interface Phase3Event {
  id: number;
  eventKey: string;
  sourceId: string;
  sessionId: string;
  sourceType: Phase3SourceType;
  droneId: number;
  trackId: number;
  frameIndex: number;
  capturedAt: string;
  ppeState: string;
  noHelmetRate: number;
  helmetRate: number;
  unknownRate: number;
  streakSeconds: number;
  estimatedDepthM: number | null;
  sceneQ33M: number | null;
  sceneQ66M: number | null;
  depthBucket: Phase3DepthBucket | null;
  enrichmentLatencyMs: number | null;
  createdAt: string;
  updatedAt: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isNullableFiniteNumber(value: unknown): value is number | null {
  return value === null || isFiniteNumber(value);
}

function isPhase3SourceType(value: unknown): value is Phase3SourceType {
  return (
    value === "SMARTPHONE_LIVE" ||
    value === "DUMMY_VIDEO" ||
    value === "DJI_LIVE"
  );
}

function isDepthBucket(
  value: unknown,
): value is Phase3DepthBucket | null {
  return (
    value === null ||
    value === "NEAR" ||
    value === "MID" ||
    value === "FAR" ||
    value === "UNKNOWN"
  );
}

function isPhase3Event(value: unknown): value is Phase3Event {
  if (!isRecord(value)) return false;

  return (
    isFiniteNumber(value.id) &&
    typeof value.eventKey === "string" &&
    typeof value.sourceId === "string" &&
    typeof value.sessionId === "string" &&
    isPhase3SourceType(value.sourceType) &&
    isFiniteNumber(value.droneId) &&
    isFiniteNumber(value.trackId) &&
    isFiniteNumber(value.frameIndex) &&
    typeof value.capturedAt === "string" &&
    typeof value.ppeState === "string" &&
    isFiniteNumber(value.noHelmetRate) &&
    isFiniteNumber(value.helmetRate) &&
    isFiniteNumber(value.unknownRate) &&
    isFiniteNumber(value.streakSeconds) &&
    isNullableFiniteNumber(value.estimatedDepthM) &&
    isNullableFiniteNumber(value.sceneQ33M) &&
    isNullableFiniteNumber(value.sceneQ66M) &&
    isDepthBucket(value.depthBucket) &&
    isNullableFiniteNumber(value.enrichmentLatencyMs) &&
    typeof value.createdAt === "string" &&
    typeof value.updatedAt === "string"
  );
}

function unwrapArray(value: unknown): unknown[] | null {
  if (Array.isArray(value)) return value;
  if (!isRecord(value)) return null;

  for (const key of ["data", "content", "items"] as const) {
    if (Array.isArray(value[key])) return value[key];
  }

  return null;
}

export function parsePhase3EventList(
  value: unknown,
): Phase3Event[] | null {
  const candidate = unwrapArray(value);
  return candidate?.every(isPhase3Event) ? candidate : null;
}
