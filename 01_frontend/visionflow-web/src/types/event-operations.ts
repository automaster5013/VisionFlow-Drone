import type { AiAlertItem } from "@/types/ai-alert";
import type {
  AiDetection,
  AiInferenceEvent,
} from "@/types/ai-inference-event";
import type { Drone } from "@/types/drone";
import type { GeofenceEvent } from "@/types/geofence";
import type { IncidentItem, IncidentSourceType } from "@/types/incident";
import type { Phase3Event } from "@/types/phase3-event";

export type EventOperationsSource =
  | "AI_ALERT"
  | "AI_INFERENCE"
  | "AI_PHASE3"
  | "GEOFENCE"
  | "INCIDENT";

export type EventOperationsSeverity = "INFO" | "WARNING" | "CRITICAL";

export type EventOperationsLifecycle =
  | "NEEDS_ACTION"
  | "MONITORING"
  | "COMPLETED";

export interface EventOperationsDetailValue {
  label: string;
  value: string;
}

export interface EventOperationsItem {
  key: string;
  source: EventOperationsSource;
  sourceId: number;
  droneId: number;
  droneLabel: string;
  sessionId: string | null;
  occurredAt: string;
  title: string;
  summary: string;
  severity: EventOperationsSeverity;
  status: string;
  statusLabel: string;
  lifecycle: EventOperationsLifecycle;
  snapshotEventId: number | null;
  snapshotAvailable: boolean;
  incidentId: number | null;
  incidentSourceType: IncidentSourceType | null;
  details: EventOperationsDetailValue[];
}

export interface EventOperationsSources {
  drones: Drone[];
  aiEvents: AiInferenceEvent[];
  phase3Events: Phase3Event[];
  aiAlerts: AiAlertItem[];
  geofenceEvents: GeofenceEvent[];
  incidents: IncidentItem[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isNullableString(value: unknown): value is string | null {
  return typeof value === "string" || value === null;
}

function isNullableFiniteNumber(value: unknown): value is number | null {
  return value === null || isFiniteNumber(value);
}

function isAiDetection(value: unknown): value is AiDetection {
  if (!isRecord(value)) return false;

  return (
    isFiniteNumber(value.id) &&
    isFiniteNumber(value.classId) &&
    typeof value.className === "string" &&
    isFiniteNumber(value.confidence) &&
    isFiniteNumber(value.x1) &&
    isFiniteNumber(value.y1) &&
    isFiniteNumber(value.x2) &&
    isFiniteNumber(value.y2)
  );
}

function isAiInferenceEvent(value: unknown): value is AiInferenceEvent {
  if (!isRecord(value)) return false;

  return (
    isFiniteNumber(value.id) &&
    typeof value.sourceId === "string" &&
    typeof value.sessionId === "string" &&
    (value.sourceType === "SMARTPHONE_LIVE" ||
      value.sourceType === "DUMMY_VIDEO" ||
      value.sourceType === "DJI_LIVE") &&
    isFiniteNumber(value.droneId) &&
    isFiniteNumber(value.frameIndex) &&
    typeof value.capturedAt === "string" &&
    typeof value.receivedAt === "string" &&
    isFiniteNumber(value.inferenceMs) &&
    isFiniteNumber(value.detectionCount) &&
    typeof value.snapshotAvailable === "boolean" &&
    isNullableString(value.snapshotUrl) &&
    (value.snapshotSizeBytes === null || isFiniteNumber(value.snapshotSizeBytes)) &&
    isNullableString(value.snapshotCreatedAt) &&
    Array.isArray(value.detections) &&
    value.detections.every(isAiDetection)
  );
}

function isGeofenceEvent(value: unknown): value is GeofenceEvent {
  if (!isRecord(value)) return false;

  return (
    isFiniteNumber(value.id) &&
    isFiniteNumber(value.droneId) &&
    typeof value.droneCode === "string" &&
    isFiniteNumber(value.geofenceId) &&
    typeof value.geofenceName === "string" &&
    (value.ruleType === "KEEP_IN" || value.ruleType === "KEEP_OUT") &&
    (value.state === "ACTIVE" || value.state === "RESOLVED") &&
    isFiniteNumber(value.latitude) &&
    isFiniteNumber(value.longitude) &&
    (value.altitude === null || isFiniteNumber(value.altitude)) &&
    isFiniteNumber(value.distanceMeters) &&
    typeof value.detectedAt === "string" &&
    isNullableString(value.resolvedAt)
  );
}

function isDrone(value: unknown): value is Drone {
  if (!isRecord(value)) return false;

  return (
    isFiniteNumber(value.id) &&
    typeof value.droneCode === "string" &&
    typeof value.name === "string" &&
    isNullableString(value.modelName) &&
    isNullableString(value.serialNumber) &&
    (value.status === "OFFLINE" ||
      value.status === "ONLINE" ||
      value.status === "FLYING" ||
      value.status === "CHARGING" ||
      value.status === "MAINTENANCE" ||
      value.status === "ERROR") &&
    isNullableString(value.rtspUrl) &&
    isNullableFiniteNumber(value.latitude) &&
    isNullableFiniteNumber(value.longitude) &&
    isNullableFiniteNumber(value.altitude) &&
    isNullableFiniteNumber(value.batteryLevel) &&
    isNullableString(value.lastConnectedAt) &&
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

export function parseEventOperationsDrones(value: unknown): Drone[] | null {
  const candidate = unwrapArray(value);
  return candidate?.every(isDrone) ? candidate : null;
}

export function parseEventOperationsAiEvents(
  value: unknown,
): AiInferenceEvent[] | null {
  const candidate = unwrapArray(value);
  return candidate?.every(isAiInferenceEvent) ? candidate : null;
}

export function parseEventOperationsGeofenceEvents(
  value: unknown,
): GeofenceEvent[] | null {
  const candidate = unwrapArray(value);
  return candidate?.every(isGeofenceEvent) ? candidate : null;
}

function sourceTypeLabel(sourceType: IncidentSourceType): string {
  return {
    AI_ALERT: "AI 경보",
    GEOFENCE: "지오펜스",
    FLIGHT_QUALITY: "기체 신뢰도",
    FLIGHT_GATE: "비행 게이트",
  }[sourceType];
}

function aiSourceLabel(sourceType: AiInferenceEvent["sourceType"]): string {
  return {
    SMARTPHONE_LIVE: "스마트폰 라이브",
    DUMMY_VIDEO: "더미 영상",
    DJI_LIVE: "DJI 라이브",
  }[sourceType];
}

function confidenceLabel(value: number): string {
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function depthBucketLabel(
  value: Phase3Event["depthBucket"],
): string {
  if (value === null) return "분석 대기";
  return {
    NEAR: "근거리",
    MID: "중거리",
    FAR: "원거리",
    UNKNOWN: "미확정",
  }[value];
}

export function buildEventOperationsTimeline({
  drones,
  aiEvents,
  phase3Events,
  aiAlerts,
  geofenceEvents,
  incidents,
}: EventOperationsSources): EventOperationsItem[] {
  const droneLabelById = new Map(
    drones.map((drone) => [
      drone.id,
      `${drone.name} · ${drone.droneCode}`,
    ]),
  );
  const droneLabel = (droneId: number, fallback?: string) =>
    droneLabelById.get(droneId) ?? fallback ?? `Drone #${droneId}`;

  const alertItems: EventOperationsItem[] = aiAlerts.map((alert) => ({
    key: `AI_ALERT:${alert.id}`,
    source: "AI_ALERT",
    sourceId: alert.id,
    droneId: alert.droneId,
    droneLabel: droneLabel(alert.droneId),
    sessionId: alert.sessionId,
    occurredAt: alert.capturedAt,
    title: alert.title,
    summary: alert.summary,
    severity: alert.severity,
    status: alert.status,
    statusLabel: {
      OPEN: "미확인",
      ACKNOWLEDGED: "확인",
      RESOLVED: "해결",
    }[alert.status],
    lifecycle:
      alert.status === "OPEN"
        ? "NEEDS_ACTION"
        : alert.status === "ACKNOWLEDGED"
          ? "MONITORING"
          : "COMPLETED",
    snapshotEventId: alert.eventId,
    snapshotAvailable: alert.snapshotAvailable,
    incidentId: null,
    incidentSourceType: null,
    details: [
      { label: "주요 객체", value: alert.primaryClassName },
      { label: "최대 신뢰도", value: confidenceLabel(alert.maxConfidence) },
      { label: "탐지 수", value: `${alert.detectionCount}개` },
      { label: "경보 ID", value: `#${alert.id}` },
    ],
  }));

  const inferenceItems: EventOperationsItem[] = aiEvents.map((event) => ({
    key: `AI_INFERENCE:${event.id}`,
    source: "AI_INFERENCE",
    sourceId: event.id,
    droneId: event.droneId,
    droneLabel: droneLabel(event.droneId),
    sessionId: event.sessionId,
    occurredAt: event.capturedAt,
    title: `${event.detectionCount}개 객체 탐지`,
    summary:
      event.detectionCount > 0
        ? event.detections
            .slice(0, 4)
            .map((detection) => detection.className)
            .join(", ") || "객체 탐지 결과가 기록되었습니다."
        : "탐지 객체 없이 추론 프레임이 기록되었습니다.",
    severity: "INFO",
    status: "RECORDED",
    statusLabel: "기록됨",
    lifecycle: "COMPLETED",
    snapshotEventId: event.id,
    snapshotAvailable: event.snapshotAvailable,
    incidentId: null,
    incidentSourceType: null,
    details: [
      { label: "영상 소스", value: aiSourceLabel(event.sourceType) },
      { label: "프레임", value: `#${event.frameIndex}` },
      { label: "추론 시간", value: `${Number(event.inferenceMs).toFixed(2)}ms` },
      { label: "탐지 수", value: `${event.detectionCount}개` },
    ],
  }));

  const phase3Items: EventOperationsItem[] = phase3Events.map((event) => {
    const confirmed = event.ppeState === "CONFIRMED_NO_HELMET";
    const depthAvailable = event.estimatedDepthM !== null;
    const depthSummary = depthAvailable
      ? ` · 추정 거리 ${Number(event.estimatedDepthM).toFixed(2)}m (${depthBucketLabel(event.depthBucket)})`
      : " · Depth 분석 대기";

    return {
      key: `AI_PHASE3:${event.id}`,
      source: "AI_PHASE3",
      sourceId: event.id,
      droneId: event.droneId,
      droneLabel: droneLabel(event.droneId),
      sessionId: event.sessionId,
      occurredAt: event.capturedAt,
      title: confirmed ? "헬멧 미착용 확인" : `PPE 상태 ${event.ppeState}`,
      summary:
        `Track #${event.trackId} · 미착용 ${confidenceLabel(event.noHelmetRate)}` +
        depthSummary,
      severity: confirmed ? "CRITICAL" : "WARNING",
      status: depthAvailable ? "DEPTH_ENRICHED" : "DEPTH_PENDING",
      statusLabel: depthAvailable ? "거리 분석 완료" : "거리 분석 중",
      lifecycle: confirmed ? "NEEDS_ACTION" : "MONITORING",
      snapshotEventId: null,
      snapshotAvailable: false,
      incidentId: null,
      incidentSourceType: null,
      details: [
        { label: "PPE 상태", value: event.ppeState },
        { label: "영상 소스", value: aiSourceLabel(event.sourceType) },
        { label: "Track", value: `#${event.trackId}` },
        { label: "프레임", value: `#${event.frameIndex}` },
        { label: "미착용 비율", value: confidenceLabel(event.noHelmetRate) },
        { label: "Helmet 비율", value: confidenceLabel(event.helmetRate) },
        { label: "Unknown 비율", value: confidenceLabel(event.unknownRate) },
        {
          label: "연속 감지",
          value: `${Number(event.streakSeconds).toFixed(2)}초`,
        },
        {
          label: "추정 거리",
          value:
            event.estimatedDepthM === null
              ? "분석 대기"
              : `${Number(event.estimatedDepthM).toFixed(3)}m`,
        },
        { label: "Depth 구간", value: depthBucketLabel(event.depthBucket) },
        {
          label: "Scene Q33 / Q66",
          value:
            event.sceneQ33M === null || event.sceneQ66M === null
              ? "분석 대기"
              : `${Number(event.sceneQ33M).toFixed(3)}m / ${Number(event.sceneQ66M).toFixed(3)}m`,
        },
        {
          label: "Depth 지연",
          value:
            event.enrichmentLatencyMs === null
              ? "분석 대기"
              : `${Number(event.enrichmentLatencyMs).toFixed(2)}ms`,
        },
      ],
    };
  });

  const geofenceItems: EventOperationsItem[] = geofenceEvents.map((event) => ({
    key: `GEOFENCE:${event.id}`,
    source: "GEOFENCE",
    sourceId: event.id,
    droneId: event.droneId,
    droneLabel: droneLabel(event.droneId, event.droneCode),
    sessionId: null,
    occurredAt: event.detectedAt,
    title: `${event.geofenceName} 경계 이벤트`,
    summary:
      event.state === "ACTIVE"
        ? "지오펜스 위반이 감지되어 현재 활성 상태입니다."
        : "지오펜스 위반이 해소되어 정상 복귀했습니다.",
    severity: event.state === "ACTIVE" ? "CRITICAL" : "INFO",
    status: event.state,
    statusLabel: event.state === "ACTIVE" ? "침범 중" : "해결",
    lifecycle: event.state === "ACTIVE" ? "NEEDS_ACTION" : "COMPLETED",
    snapshotEventId: null,
    snapshotAvailable: false,
    incidentId: null,
    incidentSourceType: null,
    details: [
      {
        label: "규칙",
        value: event.ruleType === "KEEP_IN" ? "영역 내 유지" : "영역 진입 금지",
      },
      { label: "경계 거리", value: `${Number(event.distanceMeters).toFixed(1)}m` },
      {
        label: "좌표",
        value: `${Number(event.latitude).toFixed(6)}, ${Number(event.longitude).toFixed(6)}`,
      },
      { label: "지오펜스 ID", value: `#${event.geofenceId}` },
    ],
  }));

  const incidentItems: EventOperationsItem[] = incidents.map((incident) => {
    const severity: EventOperationsSeverity =
      incident.priority === "CRITICAL"
        ? "CRITICAL"
        : incident.priority === "HIGH" || incident.priority === "MEDIUM"
          ? "WARNING"
          : "INFO";
    const statusLabels = {
      OPEN: "미처리",
      IN_PROGRESS: "대응 중",
      RESOLVED: "해결",
      CLOSED: "종료",
    } as const;

    return {
      key: `INCIDENT:${incident.id}`,
      source: "INCIDENT",
      sourceId: incident.id,
      droneId: incident.droneId,
      droneLabel: droneLabel(incident.droneId),
      sessionId: incident.sessionId,
      occurredAt: incident.occurredAt,
      title: incident.title,
      summary: incident.summary,
      severity,
      status: incident.status,
      statusLabel: statusLabels[incident.status],
      lifecycle:
        incident.status === "OPEN"
          ? "NEEDS_ACTION"
          : incident.status === "IN_PROGRESS"
            ? "MONITORING"
            : "COMPLETED",
      snapshotEventId: null,
      snapshotAvailable: false,
      incidentId: incident.id,
      incidentSourceType: incident.sourceType,
      details: [
        { label: "원본", value: sourceTypeLabel(incident.sourceType) },
        { label: "우선순위", value: incident.priority },
        { label: "담당자", value: incident.assignee ?? "미배정" },
        {
          label: "SLA",
          value: incident.slaBreachedAt
            ? `초과 · Lv.${incident.escalationLevel}`
            : incident.slaDueAt
              ? "기한 추적 중"
              : "미설정",
        },
      ],
    };
  });

  return [
    ...alertItems,
    ...inferenceItems,
    ...phase3Items,
    ...geofenceItems,
    ...incidentItems,
  ].sort((first, second) => {
    const firstTime = Date.parse(first.occurredAt);
    const secondTime = Date.parse(second.occurredAt);
    return (Number.isFinite(secondTime) ? secondTime : 0) -
      (Number.isFinite(firstTime) ? firstTime : 0);
  });
}
