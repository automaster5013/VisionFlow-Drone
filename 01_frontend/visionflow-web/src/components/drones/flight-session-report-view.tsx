"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { useOperatorAccess } from "@/components/security/operator-access-provider";
import type { AiInferenceEvent } from "@/types/ai-inference-event";
import type { Drone } from "@/types/drone";
import {
  isPersistedFlightQualityAssessment,
  type PersistedFlightQualityAssessment,
} from "@/types/flight-quality-assessment";
import type {
  FlightReplayTelemetry,
  FlightSessionReplay,
  FlightSessionSummary,
  FlightSessionSummaryStatus,
} from "@/types/flight-session-replay";

interface FlightSessionReportViewProps {
  droneId: number;
  sessionId: string;
}

interface RouteMetrics {
  distanceMeters: number;
  maxAltitude: number | null;
  firstBattery: number | null;
  lastBattery: number | null;
  minimumBattery: number | null;
  startCoordinate: string;
  endCoordinate: string;
  telemetrySources: string;
}

type DiagnosticSeverity = "INFO" | "WARNING" | "CRITICAL";

interface DiagnosticFinding {
  key: string;
  severity: DiagnosticSeverity;
  title: string;
  detail: string;
  recommendation: string;
}

interface FlightQualityAssessment {
  score: number;
  grade: "EXCELLENT" | "GOOD" | "CAUTION" | "RISK";
  dataScore: number;
  flightScore: number;
  aiScore: number;
  metrics: {
    coordinateCoveragePercent: number;
    batteryCoveragePercent: number;
    maximumTelemetryGapSeconds: number | null;
    unrealisticJumpCount: number;
    altitudeSpikeCount: number;
    batteryIncreaseCount: number;
    averageInferenceMs: number | null;
    detectedEventSnapshotCoveragePercent: number;
  };
  findings: DiagnosticFinding[];
}

function normalizeJavaDateTime(value: string): string {
  return value.replace(/(\.\d{3})\d+(?=Z|[+-]\d{2}:\d{2}|$)/, "$1");
}

function parseDateTime(value: string): number {
  return new Date(normalizeJavaDateTime(value)).getTime();
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return "-";
  }

  const timestamp = parseDateTime(value);

  return Number.isFinite(timestamp)
    ? new Date(timestamp).toLocaleString("ko-KR")
    : value;
}

function formatDuration(totalSeconds: number): string {
  const safeSeconds = Math.max(0, Math.round(totalSeconds));
  const hours = Math.floor(safeSeconds / 3_600);
  const minutes = Math.floor((safeSeconds % 3_600) / 60);
  const seconds = safeSeconds % 60;

  if (hours > 0) {
    return `${hours}시간 ${minutes}분 ${seconds}초`;
  }

  return `${minutes}분 ${seconds}초`;
}

function formatDistance(distanceMeters: number): string {
  return distanceMeters >= 1_000
    ? `${(distanceMeters / 1_000).toFixed(2)} km`
    : `${Math.round(distanceMeters)} m`;
}

function isSessionStatus(value: unknown): value is FlightSessionSummaryStatus {
  return (
    value === "READY" ||
    value === "ACTIVE" ||
    value === "COMPLETED" ||
    value === "ABORTED" ||
    value === "LEGACY"
  );
}

function isSessionSummary(value: unknown): value is FlightSessionSummary {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Partial<FlightSessionSummary>;

  return (
    typeof candidate.sessionId === "string" &&
    typeof candidate.droneId === "number" &&
    typeof candidate.name === "string" &&
    (typeof candidate.description === "string" ||
      candidate.description === null) &&
    isSessionStatus(candidate.status) &&
    (typeof candidate.sourceDeviceId === "string" ||
      candidate.sourceDeviceId === null) &&
    typeof candidate.startedAt === "string" &&
    typeof candidate.endedAt === "string" &&
    typeof candidate.durationSeconds === "number" &&
    typeof candidate.telemetryCount === "number" &&
    typeof candidate.aiEventCount === "number" &&
    typeof candidate.detectionCount === "number" &&
    typeof candidate.hasTelemetry === "boolean" &&
    typeof candidate.hasAiEvents === "boolean" &&
    typeof candidate.managed === "boolean"
  );
}

function isReplayResponse(value: unknown): value is FlightSessionReplay {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Partial<FlightSessionReplay>;

  return (
    typeof candidate.sessionId === "string" &&
    typeof candidate.droneId === "number" &&
    typeof candidate.startedAt === "string" &&
    typeof candidate.endedAt === "string" &&
    typeof candidate.durationSeconds === "number" &&
    typeof candidate.telemetryCount === "number" &&
    typeof candidate.aiEventCount === "number" &&
    typeof candidate.detectionCount === "number" &&
    Array.isArray(candidate.telemetry) &&
    Array.isArray(candidate.aiEvents)
  );
}

function isDrone(value: unknown): value is Drone {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Partial<Drone>;

  return (
    typeof candidate.id === "number" &&
    typeof candidate.droneCode === "string" &&
    typeof candidate.name === "string"
  );
}

function extractDrone(value: unknown): Drone | null {
  if (isDrone(value)) {
    return value;
  }

  if (
    typeof value === "object" &&
    value !== null &&
    "data" in value &&
    isDrone(value.data)
  ) {
    return value.data;
  }

  return null;
}

async function readErrorMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const payload: unknown = await response.json();

    if (
      typeof payload === "object" &&
      payload !== null &&
      "message" in payload &&
      typeof payload.message === "string"
    ) {
      return payload.message;
    }
  } catch {
    return fallback;
  }

  return fallback;
}

function numericValue(value: number | string | null): number | null {
  if (value === null) {
    return null;
  }

  const parsed = Number(value);

  return Number.isFinite(parsed) ? parsed : null;
}

function telemetryCoordinate(
  telemetry: FlightReplayTelemetry,
): { latitude: number; longitude: number } | null {
  const latitude = numericValue(telemetry.latitude);
  const longitude = numericValue(telemetry.longitude);

  if (latitude === null || longitude === null) {
    return null;
  }

  return { latitude, longitude };
}

function haversineDistanceMeters(
  first: { latitude: number; longitude: number },
  second: { latitude: number; longitude: number },
): number {
  const earthRadiusMeters = 6_371_000;
  const toRadians = (value: number) => (value * Math.PI) / 180;
  const latitudeDelta = toRadians(second.latitude - first.latitude);
  const longitudeDelta = toRadians(second.longitude - first.longitude);
  const firstLatitude = toRadians(first.latitude);
  const secondLatitude = toRadians(second.latitude);
  const haversine =
    Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(firstLatitude) *
      Math.cos(secondLatitude) *
      Math.sin(longitudeDelta / 2) ** 2;

  return (
    2 *
    earthRadiusMeters *
    Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine))
  );
}

function coordinateLabel(
  coordinate: { latitude: number; longitude: number } | null,
): string {
  return coordinate
    ? `${coordinate.latitude.toFixed(6)}, ${coordinate.longitude.toFixed(6)}`
    : "-";
}

function buildRouteMetrics(telemetry: FlightReplayTelemetry[]): RouteMetrics {
  const coordinates = telemetry
    .map(telemetryCoordinate)
    .filter(
      (
        coordinate,
      ): coordinate is { latitude: number; longitude: number } =>
        coordinate !== null,
    );
  let distanceMeters = 0;

  for (let index = 1; index < coordinates.length; index += 1) {
    distanceMeters += haversineDistanceMeters(
      coordinates[index - 1],
      coordinates[index],
    );
  }

  const altitudes = telemetry
    .map((point) => numericValue(point.altitude))
    .filter((value): value is number => value !== null);
  const batteries = telemetry
    .map((point) => point.batteryLevel)
    .filter((value): value is number => value !== null);
  const sources = Array.from(
    new Set(
      telemetry
        .map((point) => point.telemetrySource.trim())
        .filter(Boolean),
    ),
  );

  return {
    distanceMeters,
    maxAltitude: altitudes.length > 0 ? Math.max(...altitudes) : null,
    firstBattery: batteries.at(0) ?? null,
    lastBattery: batteries.at(-1) ?? null,
    minimumBattery: batteries.length > 0 ? Math.min(...batteries) : null,
    startCoordinate: coordinateLabel(coordinates.at(0) ?? null),
    endCoordinate: coordinateLabel(coordinates.at(-1) ?? null),
    telemetrySources: sources.length > 0 ? sources.join(", ") : "-",
  };
}

function assessmentCoordinate(
  telemetry: FlightReplayTelemetry,
): { latitude: number; longitude: number } | null {
  const coordinate = telemetryCoordinate(telemetry);

  if (
    !coordinate ||
    coordinate.latitude < -90 ||
    coordinate.latitude > 90 ||
    coordinate.longitude < -180 ||
    coordinate.longitude > 180
  ) {
    return null;
  }

  return coordinate;
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function buildQualityAssessment(
  replay: FlightSessionReplay,
  status: FlightSessionSummaryStatus,
): FlightQualityAssessment {
  const telemetryCount = replay.telemetry.length;
  const validCoordinateCount = replay.telemetry.filter(
    (point) => assessmentCoordinate(point) !== null,
  ).length;
  const batteryCount = replay.telemetry.filter(
    (point) => point.batteryLevel !== null,
  ).length;
  const coordinateCoverage =
    telemetryCount > 0 ? validCoordinateCount / telemetryCount : 0;
  const batteryCoverage =
    telemetryCount > 0 ? batteryCount / telemetryCount : 0;
  const chronologicalTelemetry = replay.telemetry
    .map((point) => ({
      point,
      timestamp: parseDateTime(point.recordedAt),
    }))
    .filter((sample) => Number.isFinite(sample.timestamp))
    .sort((left, right) => left.timestamp - right.timestamp);
  const telemetryGaps: number[] = [];
  let unrealisticJumpCount = 0;
  let altitudeSpikeCount = 0;
  let batteryIncreaseCount = 0;

  for (let index = 1; index < chronologicalTelemetry.length; index += 1) {
    const previous = chronologicalTelemetry[index - 1];
    const current = chronologicalTelemetry[index];
    const elapsedSeconds = (current.timestamp - previous.timestamp) / 1_000;

    if (elapsedSeconds <= 0) {
      continue;
    }

    telemetryGaps.push(elapsedSeconds);
    const previousCoordinate = assessmentCoordinate(previous.point);
    const currentCoordinate = assessmentCoordinate(current.point);

    if (previousCoordinate && currentCoordinate) {
      const speedMetersPerSecond =
        haversineDistanceMeters(previousCoordinate, currentCoordinate) /
        elapsedSeconds;

      if (speedMetersPerSecond > 60) {
        unrealisticJumpCount += 1;
      }
    }

    const previousAltitude = numericValue(previous.point.altitude);
    const currentAltitude = numericValue(current.point.altitude);

    if (
      previousAltitude !== null &&
      currentAltitude !== null &&
      elapsedSeconds <= 5 &&
      Math.abs(currentAltitude - previousAltitude) > 30
    ) {
      altitudeSpikeCount += 1;
    }

    if (
      previous.point.batteryLevel !== null &&
      current.point.batteryLevel !== null &&
      current.point.batteryLevel - previous.point.batteryLevel > 3
    ) {
      batteryIncreaseCount += 1;
    }
  }

  const maximumTelemetryGapSeconds =
    telemetryGaps.length > 0 ? Math.max(...telemetryGaps) : null;
  const inferenceTimes = replay.aiEvents
    .map((event) => Number(event.inferenceMs))
    .filter(Number.isFinite);
  const averageInferenceMs =
    inferenceTimes.length > 0
      ? inferenceTimes.reduce((sum, value) => sum + value, 0) /
        inferenceTimes.length
      : null;
  const detectedEvents = replay.aiEvents.filter(
    (event) => event.detectionCount > 0,
  );
  const detectedEventSnapshotCoverage =
    detectedEvents.length > 0
      ? detectedEvents.filter((event) => event.snapshotAvailable).length /
        detectedEvents.length
      : 1;
  const baseDataScore =
    telemetryCount >= 2 ? 10 : telemetryCount === 1 ? 5 : 0;
  const coordinateScore = coordinateCoverage * 15;
  const cadenceScore =
    maximumTelemetryGapSeconds === null
      ? 0
      : maximumTelemetryGapSeconds <= 3
        ? 15
        : maximumTelemetryGapSeconds <= 10
          ? 10
          : maximumTelemetryGapSeconds <= 30
            ? 5
            : 0;
  const dataScore = Math.round(
    baseDataScore + coordinateScore + cadenceScore,
  );
  const jumpScore = Math.max(0, 12 - unrealisticJumpCount * 4);
  const altitudeScore = Math.max(0, 8 - altitudeSpikeCount * 2);
  const batteryDataScore = batteryCoverage * 5;
  const batteryConsistencyScore =
    batteryCount > 0
      ? Math.max(0, 5 - batteryIncreaseCount * 2)
      : 0;
  const flightScore = Math.round(
    jumpScore +
      altitudeScore +
      batteryDataScore +
      batteryConsistencyScore,
  );
  const eventScore = replay.aiEvents.length > 0 ? 15 : 0;
  const inferenceScore =
    averageInferenceMs === null
      ? 0
      : averageInferenceMs <= 200
        ? 10
        : averageInferenceMs <= 500
          ? 7
          : averageInferenceMs <= 1_000
            ? 3
            : 0;
  const snapshotScore =
    replay.aiEvents.length > 0
      ? detectedEventSnapshotCoverage * 5
      : 0;
  const aiScore = Math.round(eventScore + inferenceScore + snapshotScore);
  const findings: DiagnosticFinding[] = [];

  if (status === "ABORTED") {
    findings.push({
      key: "aborted-session",
      severity: "CRITICAL",
      title: "비행 세션이 중단 상태입니다.",
      detail: "정상 완료가 아닌 ABORTED 상태로 종료되었습니다.",
      recommendation: "중단 원인과 당시 관제·이벤트 기록을 함께 확인하세요.",
    });
  }

  if (telemetryCount < 2) {
    findings.push({
      key: "insufficient-telemetry",
      severity: "CRITICAL",
      title: "텔레메트리 표본이 부족합니다.",
      detail: `저장된 텔레메트리가 ${telemetryCount}개입니다.`,
      recommendation: "센서 전송 주기와 백엔드 저장 성공 여부를 확인하세요.",
    });
  } else if (coordinateCoverage < 0.8) {
    findings.push({
      key: "coordinate-coverage",
      severity: "WARNING",
      title: "유효 GPS 좌표 비율이 낮습니다.",
      detail: `유효 좌표 비율은 ${(coordinateCoverage * 100).toFixed(1)}%입니다.`,
      recommendation: "위치 권한, GPS 수신 상태와 좌표 변환 로직을 확인하세요.",
    });
  }

  if (
    telemetryCount >= 2 &&
    (maximumTelemetryGapSeconds === null ||
      maximumTelemetryGapSeconds > 10)
  ) {
    findings.push({
      key: "telemetry-gap",
      severity: "WARNING",
      title: "텔레메트리 수신 공백이 큽니다.",
      detail:
        maximumTelemetryGapSeconds === null
          ? "유효한 기록 시각 간격을 계산할 수 없습니다."
          : `최대 수신 공백은 ${maximumTelemetryGapSeconds.toFixed(1)}초입니다.`,
      recommendation: "네트워크 연결과 모바일 전송 간격을 점검하세요.",
    });
  }

  if (unrealisticJumpCount > 0) {
    findings.push({
      key: "gps-jump",
      severity: "WARNING",
      title: "비현실적인 GPS 위치 이동이 감지됐습니다.",
      detail: `초속 60m를 초과한 좌표 변화가 ${unrealisticJumpCount}회입니다.`,
      recommendation: "GPS 정확도 값과 위치 스파이크 필터 적용을 검토하세요.",
    });
  }

  if (altitudeSpikeCount > 0) {
    findings.push({
      key: "altitude-spike",
      severity: "WARNING",
      title: "급격한 고도 변화가 감지됐습니다.",
      detail: `5초 이내 30m를 초과한 고도 변화가 ${altitudeSpikeCount}회입니다.`,
      recommendation: "고도 센서 보정과 이상치 제거 기준을 확인하세요.",
    });
  }

  const batteries = replay.telemetry
    .map((point) => point.batteryLevel)
    .filter((value): value is number => value !== null);
  const minimumBattery =
    batteries.length > 0 ? Math.min(...batteries) : null;

  if (telemetryCount > 0 && batteryCoverage < 0.8) {
    findings.push({
      key: "battery-coverage",
      severity: "WARNING",
      title: "배터리 텔레메트리 비율이 낮습니다.",
      detail: `배터리 값 보존율은 ${(batteryCoverage * 100).toFixed(1)}%입니다.`,
      recommendation: "배터리 센서 값과 텔레메트리 전송 DTO를 확인하세요.",
    });
  }

  if (minimumBattery !== null && minimumBattery < 15) {
    findings.push({
      key: "critical-battery",
      severity: "CRITICAL",
      title: "배터리가 위험 수준까지 내려갔습니다.",
      detail: `최저 배터리는 ${minimumBattery}%입니다.`,
      recommendation: "저전력 복귀·착륙 기준과 경보 동작을 확인하세요.",
    });
  } else if (minimumBattery !== null && minimumBattery < 25) {
    findings.push({
      key: "low-battery",
      severity: "WARNING",
      title: "배터리 잔량이 낮았습니다.",
      detail: `최저 배터리는 ${minimumBattery}%입니다.`,
      recommendation: "다음 비행에서는 충분한 복귀 여유를 확보하세요.",
    });
  }

  if (batteryIncreaseCount > 0) {
    findings.push({
      key: "battery-increase",
      severity: "INFO",
      title: "비행 중 배터리 값 상승이 관찰됐습니다.",
      detail: `3%p를 초과한 상승이 ${batteryIncreaseCount}회입니다.`,
      recommendation: "센서 반올림·보정 또는 더미 데이터 생성 규칙을 확인하세요.",
    });
  }

  if (replay.aiEvents.length === 0) {
    findings.push({
      key: "missing-ai-events",
      severity: "WARNING",
      title: "저장된 AI 추론 이벤트가 없습니다.",
      detail: "비행 세션과 연결된 AI 분석 기록이 0건입니다.",
      recommendation: "영상 입력 세션 ID와 AI 이벤트 전송 상태를 확인하세요.",
    });
  } else if (averageInferenceMs !== null && averageInferenceMs > 1_000) {
    findings.push({
      key: "critical-ai-latency",
      severity: "CRITICAL",
      title: "AI 추론 지연이 매우 큽니다.",
      detail: `평균 추론 시간은 ${averageInferenceMs.toFixed(1)}ms입니다.`,
      recommendation: "입력 해상도·프레임 주기·모델 크기와 실행 장치를 조정하세요.",
    });
  } else if (averageInferenceMs !== null && averageInferenceMs > 500) {
    findings.push({
      key: "ai-latency",
      severity: "WARNING",
      title: "AI 추론 지연을 개선할 필요가 있습니다.",
      detail: `평균 추론 시간은 ${averageInferenceMs.toFixed(1)}ms입니다.`,
      recommendation: "프레임 크기 또는 추론 주기를 낮춰 부하를 확인하세요.",
    });
  }

  if (detectedEvents.length > 0 && detectedEventSnapshotCoverage < 1) {
    findings.push({
      key: "snapshot-coverage",
      severity: "WARNING",
      title: "일부 탐지 이벤트에 증적 이미지가 없습니다.",
      detail: `탐지 이벤트 스냅샷 보존율은 ${(detectedEventSnapshotCoverage * 100).toFixed(1)}%입니다.`,
      recommendation: "AI 스냅샷 업로드와 백엔드 저장소 상태를 확인하세요.",
    });
  }

  if (findings.length === 0) {
    findings.push({
      key: "no-anomaly",
      severity: "INFO",
      title: "규칙 기반 진단에서 특이사항이 발견되지 않았습니다.",
      detail: "텔레메트리와 AI 처리 지표가 현재 진단 기준을 충족합니다.",
      recommendation: "발표 전 동일 조건으로 반복 비행해 재현성을 확인하세요.",
    });
  }

  const hasCriticalFinding = findings.some(
    (finding) => finding.severity === "CRITICAL",
  );
  const rawScore = clampScore(dataScore + flightScore + aiScore);
  const score = hasCriticalFinding ? Math.min(rawScore, 74) : rawScore;
  const grade =
    score >= 90
      ? "EXCELLENT"
      : score >= 75
        ? "GOOD"
        : score >= 60
          ? "CAUTION"
          : "RISK";

  return {
    score,
    grade,
    dataScore,
    flightScore,
    aiScore,
    metrics: {
      coordinateCoveragePercent: coordinateCoverage * 100,
      batteryCoveragePercent: batteryCoverage * 100,
      maximumTelemetryGapSeconds,
      unrealisticJumpCount,
      altitudeSpikeCount,
      batteryIncreaseCount,
      averageInferenceMs,
      detectedEventSnapshotCoveragePercent:
        detectedEventSnapshotCoverage * 100,
    },
    findings,
  };
}

function mergePersistedQualityAssessment(
  calculated: FlightQualityAssessment,
  persisted: PersistedFlightQualityAssessment,
): FlightQualityAssessment {
  return {
    ...calculated,
    score: persisted.score,
    grade: persisted.grade,
    dataScore: persisted.dataScore,
    flightScore: persisted.flightScore,
    aiScore: persisted.aiScore,
    metrics: {
      coordinateCoveragePercent:
        persisted.metrics.coordinateCoveragePercent,
      batteryCoveragePercent: persisted.metrics.batteryCoveragePercent,
      maximumTelemetryGapSeconds:
        persisted.metrics.maxTelemetryGapSeconds,
      unrealisticJumpCount: persisted.metrics.unrealisticJumpCount,
      altitudeSpikeCount: persisted.metrics.altitudeSpikeCount,
      batteryIncreaseCount: persisted.metrics.batteryIncreaseCount,
      averageInferenceMs: persisted.metrics.averageInferenceMs,
      detectedEventSnapshotCoveragePercent:
        persisted.metrics.snapshotCoveragePercent,
    },
  };
}

function statusLabel(status: FlightSessionSummaryStatus): string {
  return {
    READY: "준비",
    ACTIVE: "비행 중",
    COMPLETED: "완료",
    ABORTED: "중단",
    LEGACY: "레거시",
  }[status];
}

function ReportValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-4">
      <div className="text-xs font-bold text-slate-500">{label}</div>
      <div className="mt-1 break-words text-sm font-semibold text-slate-900">
        {value}
      </div>
    </div>
  );
}

function qualityGradeLabel(grade: FlightQualityAssessment["grade"]): string {
  return {
    EXCELLENT: "매우 우수",
    GOOD: "양호",
    CAUTION: "주의",
    RISK: "위험",
  }[grade];
}

function severityPresentation(severity: DiagnosticSeverity) {
  return {
    INFO: {
      label: "안내",
      className: "border-sky-200 bg-sky-50 text-sky-900",
      badgeClassName: "bg-sky-600 text-white",
    },
    WARNING: {
      label: "주의",
      className: "border-amber-200 bg-amber-50 text-amber-950",
      badgeClassName: "bg-amber-500 text-white",
    },
    CRITICAL: {
      label: "위험",
      className: "border-rose-200 bg-rose-50 text-rose-950",
      badgeClassName: "bg-rose-600 text-white",
    },
  }[severity];
}

function safeFileToken(value: string): string {
  return (
    value
      .trim()
      .replace(/[^a-zA-Z0-9가-힣_-]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 64) || "flight-session"
  );
}

function downloadJson(filename: string, payload: unknown): void {
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], {
    type: "application/json;charset=utf-8",
  });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");

  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.hidden = true;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

export function FlightSessionReportView({
  droneId,
  sessionId,
}: FlightSessionReportViewProps) {
  const { canOperate, operateDeniedReason } = useOperatorAccess();
  const [replay, setReplay] = useState<FlightSessionReplay | null>(null);
  const [session, setSession] = useState<FlightSessionSummary | null>(null);
  const [drone, setDrone] = useState<Drone | null>(null);
  const [persistedQuality, setPersistedQuality] =
    useState<PersistedFlightQualityAssessment | null>(null);
  const [qualityStorageNotice, setQualityStorageNotice] = useState<
    string | null
  >(null);
  const [qualitySaving, setQualitySaving] = useState(false);
  const [qualitySaveMessage, setQualitySaveMessage] = useState<string | null>(
    null,
  );
  const [qualitySaveError, setQualitySaveError] = useState<string | null>(null);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const abortController = new AbortController();

    async function loadReport() {
      try {
        const replayResponse = await fetch(
          `/api/drones/${droneId}/flight-sessions/` +
            `${encodeURIComponent(sessionId)}/replay` +
            "?telemetryLimit=5000&eventLimit=1000",
          {
            method: "GET",
            headers: { Accept: "application/json" },
            cache: "no-store",
            signal: abortController.signal,
          },
        );

        if (!replayResponse.ok) {
          throw new Error(
            await readErrorMessage(
              replayResponse,
              `통합 리플레이 조회 실패: ${replayResponse.status}`,
            ),
          );
        }

        const replayPayload: unknown = await replayResponse.json();

        if (
          !isReplayResponse(replayPayload) ||
          replayPayload.droneId !== droneId ||
          replayPayload.sessionId !== sessionId
        ) {
          throw new Error("비행 세션 리플레이 응답 형식이 올바르지 않습니다.");
        }

        setReplay(replayPayload);
        setGeneratedAt(new Date().toISOString());

        const searchParams = new URLSearchParams({
          limit: "20",
          query: sessionId,
        });
        const qualityUrl =
          `/api/drones/${droneId}/flight-sessions/` +
          `${encodeURIComponent(sessionId)}/quality-assessment`;
        const [sessionResult, droneResult, qualityResult] =
          await Promise.allSettled([
            fetch(`/api/drones/${droneId}/flight-sessions?${searchParams}`, {
              method: "GET",
              headers: { Accept: "application/json" },
              cache: "no-store",
              signal: abortController.signal,
            }).then(async (response) => {
              if (!response.ok) {
                return null;
              }

              const payload: unknown = await response.json();

              if (!Array.isArray(payload)) {
                return null;
              }

              return (
                payload
                  .filter(isSessionSummary)
                  .find((item) => item.sessionId === sessionId) ?? null
              );
            }),
            fetch(`/api/drones/${droneId}`, {
              method: "GET",
              headers: { Accept: "application/json" },
              cache: "no-store",
              signal: abortController.signal,
            }).then(async (response) => {
              if (!response.ok) {
                return null;
              }

              return extractDrone(await response.json());
            }),
            fetch(qualityUrl, {
              method: "GET",
              headers: { Accept: "application/json" },
              cache: "no-store",
              signal: abortController.signal,
            }).then(async (response) => {
              if (response.status === 404) {
                return null;
              }
              if (!response.ok) {
                throw new Error(
                  await readErrorMessage(
                    response,
                    `저장 품질 평가 조회 실패: ${response.status}`,
                  ),
                );
              }

              const payload: unknown = await response.json();

              if (
                !isPersistedFlightQualityAssessment(payload) ||
                payload.droneId !== droneId ||
                payload.sessionId !== sessionId
              ) {
                throw new Error(
                  "저장 품질 평가 응답 형식이 올바르지 않습니다.",
                );
              }

              return payload;
            }),
          ]);

        if (sessionResult.status === "fulfilled") {
          setSession(sessionResult.value);
        }
        if (droneResult.status === "fulfilled") {
          setDrone(droneResult.value);
        }
        if (qualityResult.status === "fulfilled") {
          setPersistedQuality(qualityResult.value);
          setQualityStorageNotice(
            qualityResult.value
              ? null
              : "저장 평가가 없어 현재 리플레이를 브라우저에서 임시 계산했습니다.",
          );
        } else {
          setPersistedQuality(null);
          setQualityStorageNotice(
            qualityResult.reason instanceof Error
              ? `${qualityResult.reason.message} 브라우저 임시 계산값을 표시합니다.`
              : "저장 평가를 읽지 못해 브라우저 임시 계산값을 표시합니다.",
          );
        }
        setError(null);
      } catch (loadError) {
        if (
          loadError instanceof DOMException &&
          loadError.name === "AbortError"
        ) {
          return;
        }

        setError(
          loadError instanceof Error
            ? loadError.message
            : "비행 세션 보고서를 작성하지 못했습니다.",
        );
      } finally {
        if (!abortController.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void loadReport();

    return () => abortController.abort();
  }, [droneId, sessionId]);

  const routeMetrics = useMemo(
    () => buildRouteMetrics(replay?.telemetry ?? []),
    [replay],
  );
  const calculatedQualityAssessment = useMemo(
    () =>
      replay
        ? buildQualityAssessment(
            replay,
            session?.status ?? "LEGACY",
          )
        : null,
    [replay, session?.status],
  );
  const qualityAssessment = useMemo(
    () =>
      calculatedQualityAssessment && persistedQuality
        ? mergePersistedQualityAssessment(
            calculatedQualityAssessment,
            persistedQuality,
          )
        : calculatedQualityAssessment,
    [calculatedQualityAssessment, persistedQuality],
  );

  const detectionSummary = useMemo(() => {
    const counts = new Map<string, number>();

    for (const event of replay?.aiEvents ?? []) {
      for (const detection of event.detections) {
        counts.set(
          detection.className,
          (counts.get(detection.className) ?? 0) + 1,
        );
      }
    }

    return Array.from(counts.entries()).sort(
      ([firstName, firstCount], [secondName, secondCount]) =>
        secondCount - firstCount || firstName.localeCompare(secondName),
    );
  }, [replay]);

  const snapshotEvents = useMemo(
    () =>
      (replay?.aiEvents ?? [])
        .filter((event) => event.snapshotAvailable)
        .slice(0, 8),
    [replay],
  );

  const sampledTelemetry = useMemo(() => {
    const telemetry = replay?.telemetry ?? [];

    if (telemetry.length <= 6) {
      return telemetry;
    }

    const indexes = new Set([
      0,
      Math.floor(telemetry.length * 0.2),
      Math.floor(telemetry.length * 0.4),
      Math.floor(telemetry.length * 0.6),
      Math.floor(telemetry.length * 0.8),
      telemetry.length - 1,
    ]);

    return Array.from(indexes)
      .sort((first, second) => first - second)
      .map((index) => telemetry[index]);
  }, [replay]);

  const controlHref =
    `/drones?${new URLSearchParams({
      droneId: String(droneId),
      sessionId,
    }).toString()}#flight-session-replay`;

  async function recalculateAndSaveQuality() {
    if (!canOperate || qualitySaving) {
      return;
    }

    setQualitySaving(true);
    setQualitySaveMessage(null);
    setQualitySaveError(null);

    try {
      const response = await fetch(
        `/api/drones/${droneId}/flight-sessions/` +
          `${encodeURIComponent(sessionId)}/quality-assessment`,
        {
          method: "PUT",
          headers: { Accept: "application/json" },
          cache: "no-store",
        },
      );

      if (!response.ok) {
        throw new Error(
          await readErrorMessage(
            response,
            `품질 평가 저장 실패: ${response.status}`,
          ),
        );
      }

      const payload: unknown = await response.json();

      if (
        !isPersistedFlightQualityAssessment(payload) ||
        payload.droneId !== droneId ||
        payload.sessionId !== sessionId
      ) {
        throw new Error("저장된 품질 평가 응답 형식이 올바르지 않습니다.");
      }

      setPersistedQuality(payload);
      setQualityStorageNotice(null);
      setQualitySaveMessage(
        `${formatDateTime(payload.evaluatedAt)} 기준으로 MySQL에 저장했습니다.`,
      );
    } catch (saveError) {
      setQualitySaveError(
        saveError instanceof Error
          ? saveError.message
          : "비행 품질 평가를 저장하지 못했습니다.",
      );
    } finally {
      setQualitySaving(false);
    }
  }

  function exportQualityEvidence() {
    if (!replay || !qualityAssessment) {
      return;
    }

    downloadJson(
      `visionflow-flight-quality-${safeFileToken(sessionId)}.json`,
      {
        schemaVersion: 1,
        project: "VisionFlow",
        evidenceType: "FLIGHT_QUALITY_ASSESSMENT",
        generatedAt: new Date().toISOString(),
        assessmentSource: persistedQuality
          ? "MYSQL_PERSISTED"
          : "BROWSER_FALLBACK",
        ruleSetVersion: persistedQuality?.ruleVersion ?? "2026-07-25.1",
        persistedAssessment: persistedQuality,
        disclaimer:
          "발표 및 운영 보조용 규칙 기반 진단이며 항공 안전 인증 결과가 아닙니다.",
        drone: drone
          ? {
              id: drone.id,
              droneCode: drone.droneCode,
              name: drone.name,
            }
          : { id: droneId },
        session: session ?? {
          sessionId,
          droneId,
          status: "LEGACY",
        },
        replaySummary: {
          startedAt: replay.startedAt,
          endedAt: replay.endedAt,
          durationSeconds: replay.durationSeconds,
          telemetryCount: replay.telemetryCount,
          aiEventCount: replay.aiEventCount,
          detectionCount: replay.detectionCount,
        },
        routeMetrics,
        qualityAssessment,
      },
    );
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-5xl p-8 text-center text-slate-500">
        비행 세션 종합 보고서를 작성하는 중입니다.
      </main>
    );
  }

  if (error || !replay) {
    return (
      <main className="mx-auto max-w-3xl p-8">
        <div className="rounded-2xl border border-red-300 bg-red-50 p-6 text-red-900">
          {error ?? "비행 세션 보고서를 표시할 수 없습니다."}
        </div>
        <Link
          href={controlHref}
          className="mt-4 inline-flex rounded-lg bg-slate-900 px-4 py-2 font-bold text-white"
        >
          관제 리플레이로 돌아가기
        </Link>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-100 px-4 py-8 print:bg-white print:p-0">
      <article className="mx-auto max-w-6xl rounded-3xl bg-white p-6 shadow-sm print:max-w-none print:rounded-none print:p-6 print:shadow-none sm:p-10">
        <header className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-6">
          <div>
            <div className="text-xs font-bold uppercase tracking-[0.2em] text-cyan-700">
              VisionFlow Drone Control Center
            </div>
            <h1 className="mt-2 text-3xl font-black text-slate-950">
              비행 세션 종합 보고서
            </h1>
            <p className="mt-2 break-all text-sm text-slate-500">
              {session?.name ?? `Flight Session ${sessionId}`}
            </p>
          </div>
          <div className="flex flex-wrap gap-2 print:hidden">
            <Link
              href={controlHref}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700"
            >
              관제 리플레이
            </Link>
            <button
              type="button"
              onClick={exportQualityEvidence}
              className="rounded-lg border border-cyan-300 bg-cyan-50 px-4 py-2 text-sm font-bold text-cyan-900"
            >
              품질 진단 JSON
            </button>
            <button
              type="button"
              onClick={() => window.print()}
              className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-bold text-white"
            >
              인쇄 / PDF 저장
            </button>
          </div>
        </header>

        <section className="mt-8">
          <h2 className="text-lg font-black text-slate-950">비행 개요</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <ReportValue
              label="드론"
              value={
                drone
                  ? `${drone.name} · ${drone.droneCode}`
                  : `Drone #${droneId}`
              }
            />
            <ReportValue
              label="세션 상태"
              value={session ? statusLabel(session.status) : "저장 완료"}
            />
            <ReportValue
              label="비행 시작"
              value={formatDateTime(replay.startedAt)}
            />
            <ReportValue
              label="비행 종료"
              value={formatDateTime(replay.endedAt)}
            />
            <ReportValue
              label="비행 시간"
              value={formatDuration(replay.durationSeconds)}
            />
            <ReportValue
              label="이동 거리"
              value={formatDistance(routeMetrics.distanceMeters)}
            />
            <ReportValue
              label="최대 고도"
              value={
                routeMetrics.maxAltitude === null
                  ? "-"
                  : `${routeMetrics.maxAltitude.toFixed(1)} m`
              }
            />
            <ReportValue
              label="텔레메트리 출처"
              value={routeMetrics.telemetrySources}
            />
          </div>
          {session?.description && (
            <p className="mt-4 whitespace-pre-wrap rounded-xl border border-slate-200 p-4 text-sm leading-7 text-slate-700">
              {session.description}
            </p>
          )}
          <div className="mt-3 break-all rounded-xl bg-slate-50 p-4 font-mono text-xs text-slate-600">
            Session ID: {sessionId}
          </div>
        </section>

        {qualityAssessment && (
          <section className="mt-8 break-inside-avoid">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-black text-slate-950">
                  비행 품질 자동 진단
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  텔레메트리 완전성·기체 값 안정성·AI 처리 상태를 규칙
                  기반으로 분석합니다.
                </p>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2 print:hidden">
                <span
                  className={
                    persistedQuality
                      ? "rounded-full bg-emerald-100 px-3 py-1 text-xs font-black text-emerald-800"
                      : "rounded-full bg-amber-100 px-3 py-1 text-xs font-black text-amber-900"
                  }
                >
                  {persistedQuality
                    ? "MySQL 저장 평가"
                    : "브라우저 임시 계산"}
                </span>
                <button
                  type="button"
                  onClick={recalculateAndSaveQuality}
                  disabled={!canOperate || qualitySaving}
                  title={
                    canOperate
                      ? "현재 저장 데이터를 기준으로 품질 평가를 다시 계산합니다."
                      : (operateDeniedReason ?? undefined)
                  }
                  className="rounded-lg border border-cyan-300 bg-cyan-50 px-3 py-2 text-xs font-black text-cyan-900 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {qualitySaving ? "평가 저장 중..." : "품질 재평가 저장"}
                </button>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs font-bold text-slate-500">
              <span>
                진단 규칙{" "}
                {persistedQuality?.ruleVersion ?? "2026-07-25.1"}
              </span>
              {persistedQuality && (
                <span>
                  · 평가 시각 {formatDateTime(persistedQuality.evaluatedAt)}
                </span>
              )}
            </div>

            {(qualityStorageNotice ||
              qualitySaveMessage ||
              qualitySaveError ||
              (!canOperate && operateDeniedReason)) && (
              <div className="mt-3 space-y-2 print:hidden">
                {qualityStorageNotice && (
                  <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                    {qualityStorageNotice}
                  </p>
                )}
                {qualitySaveMessage && (
                  <p
                    role="status"
                    className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900"
                  >
                    {qualitySaveMessage}
                  </p>
                )}
                {qualitySaveError && (
                  <p
                    role="alert"
                    className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-900"
                  >
                    {qualitySaveError}
                  </p>
                )}
                {!canOperate && operateDeniedReason && (
                  <p className="text-xs text-slate-500">
                    재평가 저장: {operateDeniedReason}
                  </p>
                )}
              </div>
            )}

            <div className="mt-4 grid gap-4 lg:grid-cols-[220px_1fr]">
              <div className="rounded-2xl bg-slate-950 p-5 text-white">
                <div className="text-xs font-bold uppercase tracking-wider text-cyan-300">
                  Flight Quality
                </div>
                <div className="mt-3 flex items-end gap-2">
                  <strong className="text-5xl font-black">
                    {qualityAssessment.score}
                  </strong>
                  <span className="pb-1 text-sm text-slate-300">/ 100</span>
                </div>
                <div className="mt-2 text-lg font-black text-cyan-300">
                  {qualityGradeLabel(qualityAssessment.grade)}
                </div>
                <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-700">
                  <div
                    className="h-full rounded-full bg-cyan-400"
                    style={{ width: `${qualityAssessment.score}%` }}
                  />
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                <QualitySubScore
                  label="데이터 완전성"
                  score={qualityAssessment.dataScore}
                  maximum={40}
                  description={`좌표 ${qualityAssessment.metrics.coordinateCoveragePercent.toFixed(0)}%`}
                />
                <QualitySubScore
                  label="비행 값 안정성"
                  score={qualityAssessment.flightScore}
                  maximum={30}
                  description={`GPS 점프 ${qualityAssessment.metrics.unrealisticJumpCount}회`}
                />
                <QualitySubScore
                  label="AI 처리 상태"
                  score={qualityAssessment.aiScore}
                  maximum={30}
                  description={
                    qualityAssessment.metrics.averageInferenceMs === null
                      ? "추론 기록 없음"
                      : `평균 ${qualityAssessment.metrics.averageInferenceMs.toFixed(1)}ms`
                  }
                />
              </div>
            </div>

            <div className="mt-4 space-y-3">
              {qualityAssessment.findings.map((finding) => (
                <DiagnosticFindingCard
                  key={finding.key}
                  finding={finding}
                />
              ))}
            </div>

            <p className="mt-4 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-500">
              이 점수는 발표 및 운영 보조를 위한 규칙 기반 진단이며 항공
              안전 인증이나 실제 기체의 비행 적합 판정을 대신하지 않습니다.
            </p>
          </section>
        )}

        <section className="mt-8 break-inside-avoid">
          <h2 className="text-lg font-black text-slate-950">
            경로·기체 지표
          </h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <ReportValue
              label="저장 좌표"
              value={`${replay.telemetryCount}개`}
            />
            <ReportValue
              label="출발 좌표"
              value={routeMetrics.startCoordinate}
            />
            <ReportValue
              label="종료 좌표"
              value={routeMetrics.endCoordinate}
            />
            <ReportValue
              label="배터리 변화"
              value={
                routeMetrics.firstBattery === null ||
                routeMetrics.lastBattery === null
                  ? "-"
                  : `${routeMetrics.firstBattery}% → ${routeMetrics.lastBattery}%`
              }
            />
            <ReportValue
              label="최저 배터리"
              value={
                routeMetrics.minimumBattery === null
                  ? "-"
                  : `${routeMetrics.minimumBattery}%`
              }
            />
          </div>
        </section>

        <section className="mt-8 break-inside-avoid">
          <h2 className="text-lg font-black text-slate-950">
            AI 영상 분석 결과
          </h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <ReportValue
              label="AI 이벤트"
              value={`${replay.aiEventCount}건`}
            />
            <ReportValue
              label="총 탐지 객체"
              value={`${replay.detectionCount}개`}
            />
            <ReportValue
              label="저장 스냅샷"
              value={`${snapshotEvents.length}개 표시`}
            />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {detectionSummary.length > 0 ? (
              detectionSummary.map(([className, count]) => (
                <span
                  key={className}
                  className="rounded-full bg-violet-100 px-3 py-1 text-sm font-bold text-violet-800"
                >
                  {className} {count}개
                </span>
              ))
            ) : (
              <span className="text-sm text-slate-500">
                저장된 탐지 객체가 없습니다.
              </span>
            )}
          </div>
        </section>

        {snapshotEvents.length > 0 && (
          <section className="mt-8">
            <h2 className="text-lg font-black text-slate-950">
              주요 탐지 스냅샷
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              저장 순서 기준 최대 8개를 보고서에 표시합니다.
            </p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              {snapshotEvents.map((event) => (
                <SnapshotEvidence key={event.id} event={event} />
              ))}
            </div>
          </section>
        )}

        <section className="mt-8">
          <h2 className="text-lg font-black text-slate-950">
            경로 표본 텔레메트리
          </h2>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="bg-slate-100 text-slate-700">
                  <th className="border border-slate-200 p-2">시각</th>
                  <th className="border border-slate-200 p-2">위도</th>
                  <th className="border border-slate-200 p-2">경도</th>
                  <th className="border border-slate-200 p-2">고도</th>
                  <th className="border border-slate-200 p-2">배터리</th>
                  <th className="border border-slate-200 p-2">출처</th>
                </tr>
              </thead>
              <tbody>
                {sampledTelemetry.map((point) => (
                  <tr key={point.id}>
                    <td className="border border-slate-200 p-2">
                      {formatDateTime(point.recordedAt)}
                    </td>
                    <td className="border border-slate-200 p-2">
                      {numericValue(point.latitude)?.toFixed(6) ?? "-"}
                    </td>
                    <td className="border border-slate-200 p-2">
                      {numericValue(point.longitude)?.toFixed(6) ?? "-"}
                    </td>
                    <td className="border border-slate-200 p-2">
                      {numericValue(point.altitude)?.toFixed(1) ?? "-"}
                    </td>
                    <td className="border border-slate-200 p-2">
                      {point.batteryLevel ?? "-"}
                    </td>
                    <td className="border border-slate-200 p-2">
                      {point.telemetrySource}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <footer className="mt-8 border-t border-slate-200 pt-4 text-xs text-slate-500">
          이 보고서는 MySQL에 저장된 VisionFlow 비행 텔레메트리와 AI 추론
          이벤트를 조회해 생성했습니다. 출력 시각:{" "}
          {formatDateTime(generatedAt)}
        </footer>
      </article>
    </main>
  );
}

function QualitySubScore({
  label,
  score,
  maximum,
  description,
}: {
  label: string;
  score: number;
  maximum: number;
  description: string;
}) {
  const percentage = Math.max(
    0,
    Math.min(100, (score / maximum) * 100),
  );

  return (
    <div className="rounded-xl border border-slate-200 p-4">
      <div className="text-xs font-bold text-slate-500">{label}</div>
      <div className="mt-2 text-2xl font-black text-slate-950">
        {score}
        <span className="ml-1 text-xs font-semibold text-slate-400">
          / {maximum}
        </span>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-cyan-600"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <div className="mt-2 text-xs text-slate-500">{description}</div>
    </div>
  );
}

function DiagnosticFindingCard({
  finding,
}: {
  finding: DiagnosticFinding;
}) {
  const presentation = severityPresentation(finding.severity);

  return (
    <div className={`rounded-xl border p-4 ${presentation.className}`}>
      <div className="flex flex-wrap items-start gap-2">
        <span
          className={`rounded-full px-2 py-1 text-[10px] font-black ${presentation.badgeClassName}`}
        >
          {presentation.label}
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-black">{finding.title}</div>
          <p className="mt-1 text-sm leading-6">{finding.detail}</p>
          <p className="mt-2 text-xs font-bold">
            권고: {finding.recommendation}
          </p>
        </div>
      </div>
    </div>
  );
}

function SnapshotEvidence({ event }: { event: AiInferenceEvent }) {
  const classNames = Array.from(
    new Set(event.detections.map((detection) => detection.className)),
  );

  return (
    <figure className="break-inside-avoid overflow-hidden rounded-xl border border-slate-200">
      <div className="bg-slate-950">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={event.snapshotUrl ?? `/api/ai/events/${event.id}/snapshot`}
          alt={`AI 탐지 이벤트 ${event.id}`}
          className="aspect-video h-full w-full object-contain"
        />
      </div>
      <figcaption className="p-3 text-xs text-slate-600">
        <div className="font-bold text-slate-900">
          Frame #{event.frameIndex} · 탐지 {event.detectionCount}개
        </div>
        <div className="mt-1">
          {formatDateTime(event.capturedAt)} ·{" "}
          {classNames.length > 0 ? classNames.join(", ") : "탐지 상세 없음"}
        </div>
      </figcaption>
    </figure>
  );
}
