import type {
  FlightReplayTelemetry,
  FlightSessionReplay,
  FlightSessionSummaryStatus,
} from "@/types/flight-session-replay";

export type FlightQualityGrade =
  | "EXCELLENT"
  | "GOOD"
  | "CAUTION"
  | "RISK";

export type FlightRiskSeverity = "WARNING" | "CRITICAL";

export interface FlightQualityRisk {
  severity: FlightRiskSeverity;
  title: string;
  detail: string;
}

export interface FlightQualitySummary {
  score: number;
  grade: FlightQualityGrade;
  dataScore: number;
  flightScore: number;
  aiScore: number;
  warningCount: number;
  criticalCount: number;
  primaryRisk: FlightQualityRisk | null;
}

function numericValue(value: number | string | null): number | null {
  if (value === null) {
    return null;
  }

  const parsed = Number(value);

  return Number.isFinite(parsed) ? parsed : null;
}

function coordinate(
  telemetry: FlightReplayTelemetry,
): { latitude: number; longitude: number } | null {
  const latitude = numericValue(telemetry.latitude);
  const longitude = numericValue(telemetry.longitude);

  if (
    latitude === null ||
    longitude === null ||
    latitude < -90 ||
    latitude > 90 ||
    longitude < -180 ||
    longitude > 180
  ) {
    return null;
  }

  return { latitude, longitude };
}

function distanceMeters(
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

function timestamp(value: string): number {
  return new Date(
    value.replace(/(\.\d{3})\d+(?=Z|[+-]\d{2}:\d{2}|$)/, "$1"),
  ).getTime();
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

export function buildFlightQualitySummary(
  replay: FlightSessionReplay,
  status: FlightSessionSummaryStatus,
): FlightQualitySummary {
  const telemetryCount = replay.telemetry.length;
  const validCoordinateCount = replay.telemetry.filter(
    (point) => coordinate(point) !== null,
  ).length;
  const batteryValues = replay.telemetry
    .map((point) => point.batteryLevel)
    .filter((value): value is number => value !== null);
  const coordinateCoverage =
    telemetryCount > 0 ? validCoordinateCount / telemetryCount : 0;
  const batteryCoverage =
    telemetryCount > 0 ? batteryValues.length / telemetryCount : 0;
  const samples = replay.telemetry
    .map((point) => ({ point, timestamp: timestamp(point.recordedAt) }))
    .filter((sample) => Number.isFinite(sample.timestamp))
    .sort((left, right) => left.timestamp - right.timestamp);
  const gaps: number[] = [];
  let unrealisticJumpCount = 0;
  let altitudeSpikeCount = 0;
  let batteryIncreaseCount = 0;

  for (let index = 1; index < samples.length; index += 1) {
    const previous = samples[index - 1];
    const current = samples[index];
    const elapsedSeconds = (current.timestamp - previous.timestamp) / 1_000;

    if (elapsedSeconds <= 0) {
      continue;
    }

    gaps.push(elapsedSeconds);
    const previousCoordinate = coordinate(previous.point);
    const currentCoordinate = coordinate(current.point);

    if (
      previousCoordinate &&
      currentCoordinate &&
      distanceMeters(previousCoordinate, currentCoordinate) /
        elapsedSeconds >
        60
    ) {
      unrealisticJumpCount += 1;
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

  const maximumGap = gaps.length > 0 ? Math.max(...gaps) : null;
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
  const snapshotCoverage =
    detectedEvents.length > 0
      ? detectedEvents.filter((event) => event.snapshotAvailable).length /
        detectedEvents.length
      : 1;
  const baseDataScore =
    telemetryCount >= 2 ? 10 : telemetryCount === 1 ? 5 : 0;
  const cadenceScore =
    maximumGap === null
      ? 0
      : maximumGap <= 3
        ? 15
        : maximumGap <= 10
          ? 10
          : maximumGap <= 30
            ? 5
            : 0;
  const dataScore = Math.round(
    baseDataScore + coordinateCoverage * 15 + cadenceScore,
  );
  const flightScore = Math.round(
    Math.max(0, 12 - unrealisticJumpCount * 4) +
      Math.max(0, 8 - altitudeSpikeCount * 2) +
      batteryCoverage * 5 +
      (batteryValues.length > 0
        ? Math.max(0, 5 - batteryIncreaseCount * 2)
        : 0),
  );
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
  const aiScore = Math.round(
    (replay.aiEvents.length > 0 ? 15 : 0) +
      inferenceScore +
      (replay.aiEvents.length > 0 ? snapshotCoverage * 5 : 0),
  );
  const risks: FlightQualityRisk[] = [];
  const minimumBattery =
    batteryValues.length > 0 ? Math.min(...batteryValues) : null;

  if (status === "ABORTED") {
    risks.push({
      severity: "CRITICAL",
      title: "중단된 비행 세션",
      detail: "중단 원인과 당시 이벤트를 확인해야 합니다.",
    });
  }
  if (telemetryCount < 2) {
    risks.push({
      severity: "CRITICAL",
      title: "텔레메트리 표본 부족",
      detail: `저장된 텔레메트리가 ${telemetryCount}개입니다.`,
    });
  } else if (coordinateCoverage < 0.8) {
    risks.push({
      severity: "WARNING",
      title: "GPS 좌표 보존율 저하",
      detail: `유효 좌표 비율 ${(coordinateCoverage * 100).toFixed(1)}%`,
    });
  }
  if (
    telemetryCount >= 2 &&
    (maximumGap === null || maximumGap > 10)
  ) {
    risks.push({
      severity: "WARNING",
      title: "텔레메트리 수신 공백",
      detail:
        maximumGap === null
          ? "기록 간격을 계산할 수 없습니다."
          : `최대 공백 ${maximumGap.toFixed(1)}초`,
    });
  }
  if (unrealisticJumpCount > 0) {
    risks.push({
      severity: "WARNING",
      title: "GPS 위치 점프",
      detail: `비현실적인 좌표 변화 ${unrealisticJumpCount}회`,
    });
  }
  if (altitudeSpikeCount > 0) {
    risks.push({
      severity: "WARNING",
      title: "고도 급변",
      detail: `급격한 고도 변화 ${altitudeSpikeCount}회`,
    });
  }
  if (telemetryCount > 0 && batteryCoverage < 0.8) {
    risks.push({
      severity: "WARNING",
      title: "배터리 값 보존율 저하",
      detail: `배터리 값 보존율 ${(batteryCoverage * 100).toFixed(1)}%`,
    });
  }
  if (minimumBattery !== null && minimumBattery < 15) {
    risks.push({
      severity: "CRITICAL",
      title: "위험 배터리",
      detail: `최저 배터리 ${minimumBattery}%`,
    });
  } else if (minimumBattery !== null && minimumBattery < 25) {
    risks.push({
      severity: "WARNING",
      title: "저전력 비행",
      detail: `최저 배터리 ${minimumBattery}%`,
    });
  }
  if (replay.aiEvents.length === 0) {
    risks.push({
      severity: "WARNING",
      title: "AI 추론 기록 없음",
      detail: "비행 세션과 연결된 AI 이벤트가 없습니다.",
    });
  } else if (averageInferenceMs !== null && averageInferenceMs > 1_000) {
    risks.push({
      severity: "CRITICAL",
      title: "AI 추론 지연 위험",
      detail: `평균 ${averageInferenceMs.toFixed(1)}ms`,
    });
  } else if (averageInferenceMs !== null && averageInferenceMs > 500) {
    risks.push({
      severity: "WARNING",
      title: "AI 추론 지연 주의",
      detail: `평균 ${averageInferenceMs.toFixed(1)}ms`,
    });
  }
  if (detectedEvents.length > 0 && snapshotCoverage < 1) {
    risks.push({
      severity: "WARNING",
      title: "탐지 증적 이미지 누락",
      detail: `스냅샷 보존율 ${(snapshotCoverage * 100).toFixed(1)}%`,
    });
  }

  risks.sort((left, right) => {
    const severityOrder = { CRITICAL: 0, WARNING: 1 };

    return severityOrder[left.severity] - severityOrder[right.severity];
  });

  const criticalCount = risks.filter(
    (risk) => risk.severity === "CRITICAL",
  ).length;
  const warningCount = risks.length - criticalCount;
  const rawScore = clampScore(dataScore + flightScore + aiScore);
  const score = criticalCount > 0 ? Math.min(rawScore, 74) : rawScore;
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
    warningCount,
    criticalCount,
    primaryRisk: risks[0] ?? null,
  };
}
