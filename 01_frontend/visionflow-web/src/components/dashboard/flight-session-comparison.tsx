"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import type {
  DashboardFlightSessionItem,
} from "@/types/operations-dashboard";
import type {
  FlightReplayTelemetry,
  FlightSessionReplay,
} from "@/types/flight-session-replay";

interface ComparisonResult {
  left: FlightSessionReplay;
  right: FlightSessionReplay;
}

interface ReplayMetrics {
  distanceMeters: number;
  maxAltitude: number | null;
  minimumBattery: number | null;
  batteryConsumption: number | null;
  averageInferenceMs: number | null;
  detectionsPerMinute: number;
}

interface MetricRow {
  label: string;
  left: string;
  right: string;
  delta: string;
}

interface FlightSessionComparisonProps {
  initialLeftKey?: string;
  initialRightKey?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isComparableSession(
  value: unknown,
): value is DashboardFlightSessionItem {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.sessionId === "string" &&
    typeof value.droneId === "number" &&
    typeof value.name === "string" &&
    (value.description === null || typeof value.description === "string") &&
    (value.status === "COMPLETED" || value.status === "ABORTED") &&
    (value.sourceDeviceId === null ||
      typeof value.sourceDeviceId === "string") &&
    typeof value.startedAt === "string" &&
    (value.endedAt === null || typeof value.endedAt === "string") &&
    typeof value.durationSeconds === "number"
  );
}

function extractComparableSessions(
  value: unknown,
): DashboardFlightSessionItem[] | null {
  const candidate = isRecord(value) && isRecord(value.data) ? value.data : value;

  if (
    !isRecord(candidate) ||
    !Array.isArray(candidate.recentSessions)
  ) {
    return null;
  }

  return candidate.recentSessions.filter(isComparableSession);
}

function isReplayResponse(value: unknown): value is FlightSessionReplay {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.sessionId === "string" &&
    typeof value.droneId === "number" &&
    typeof value.startedAt === "string" &&
    typeof value.endedAt === "string" &&
    typeof value.durationSeconds === "number" &&
    typeof value.telemetryCount === "number" &&
    typeof value.aiEventCount === "number" &&
    typeof value.detectionCount === "number" &&
    Array.isArray(value.telemetry) &&
    Array.isArray(value.aiEvents)
  );
}

async function readErrorMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const payload: unknown = await response.json();

    if (
      isRecord(payload) &&
      typeof payload.message === "string"
    ) {
      return payload.message;
    }
  } catch {
    return fallback;
  }

  return fallback;
}

function sessionKey(session: DashboardFlightSessionItem): string {
  return `${session.droneId}|${session.sessionId}`;
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

  return latitude === null || longitude === null
    ? null
    : { latitude, longitude };
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

function replayMetrics(replay: FlightSessionReplay): ReplayMetrics {
  const coordinates = replay.telemetry
    .map(coordinate)
    .filter(
      (
        value,
      ): value is { latitude: number; longitude: number } =>
        value !== null,
    );
  let distanceMeters = 0;

  for (let index = 1; index < coordinates.length; index += 1) {
    distanceMeters += haversineDistanceMeters(
      coordinates[index - 1],
      coordinates[index],
    );
  }

  const altitudes = replay.telemetry
    .map((point) => numericValue(point.altitude))
    .filter((value): value is number => value !== null);
  const batteries = replay.telemetry
    .map((point) => point.batteryLevel)
    .filter((value): value is number => value !== null);
  const inferenceTimes = replay.aiEvents
    .map((event) => Number(event.inferenceMs))
    .filter(Number.isFinite);
  const firstBattery = batteries.at(0) ?? null;
  const lastBattery = batteries.at(-1) ?? null;

  return {
    distanceMeters,
    maxAltitude: altitudes.length > 0 ? Math.max(...altitudes) : null,
    minimumBattery: batteries.length > 0 ? Math.min(...batteries) : null,
    batteryConsumption:
      firstBattery === null || lastBattery === null
        ? null
        : firstBattery - lastBattery,
    averageInferenceMs:
      inferenceTimes.length > 0
        ? inferenceTimes.reduce((sum, value) => sum + value, 0) /
          inferenceTimes.length
        : null,
    detectionsPerMinute:
      replay.durationSeconds > 0
        ? replay.detectionCount / (replay.durationSeconds / 60)
        : 0,
  };
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return "-";
  }

  const normalized = value.replace(
    /(\.\d{3})\d+(?=Z|[+-]\d{2}:\d{2}|$)/,
    "$1",
  );
  const timestamp = new Date(normalized);

  return Number.isNaN(timestamp.getTime())
    ? value
    : timestamp.toLocaleString("ko-KR");
}

function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  const minutes = Math.floor(seconds / 60);

  return `${minutes}분 ${seconds % 60}초`;
}

function formatDistance(value: number): string {
  return value >= 1_000
    ? `${(value / 1_000).toFixed(2)} km`
    : `${Math.round(value)} m`;
}

function signedNumber(value: number, unit: string, digits = 0): string {
  const sign = value > 0 ? "+" : "";

  return `${sign}${value.toFixed(digits)}${unit}`;
}

async function loadReplay(
  session: DashboardFlightSessionItem,
  signal: AbortSignal,
): Promise<FlightSessionReplay> {
  const response = await fetch(
    `/api/drones/${session.droneId}/flight-sessions/` +
      `${encodeURIComponent(session.sessionId)}/replay` +
      "?telemetryLimit=5000&eventLimit=1000",
    {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal,
    },
  );

  if (!response.ok) {
    throw new Error(
      await readErrorMessage(
        response,
        `${session.name} 리플레이 조회 실패: ${response.status}`,
      ),
    );
  }

  const payload: unknown = await response.json();

  if (
    !isReplayResponse(payload) ||
    payload.droneId !== session.droneId ||
    payload.sessionId !== session.sessionId
  ) {
    throw new Error(`${session.name} 리플레이 응답 형식이 올바르지 않습니다.`);
  }

  return payload;
}

function reportHref(session: DashboardFlightSessionItem): string {
  return (
    `/drones/${session.droneId}/flight-sessions/` +
    `${encodeURIComponent(session.sessionId)}/report`
  );
}

function replayHref(session: DashboardFlightSessionItem): string {
  const params = new URLSearchParams({
    droneId: String(session.droneId),
    sessionId: session.sessionId,
  });

  return `/drones?${params.toString()}#flight-session-replay`;
}

function comparisonPath(leftKey: string, rightKey: string): string {
  const params = new URLSearchParams({
    left: leftKey,
    right: rightKey,
  });

  return `/flight-comparison?${params.toString()}`;
}

function safeFileToken(value: string): string {
  return value
    .trim()
    .replace(/[^a-zA-Z0-9가-힣_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48) || "flight";
}

function comparisonFileBase(
  leftSession: DashboardFlightSessionItem,
  rightSession: DashboardFlightSessionItem,
): string {
  return (
    `visionflow-flight-comparison-` +
    `${safeFileToken(leftSession.sessionId)}-vs-` +
    safeFileToken(rightSession.sessionId)
  );
}

function downloadTextFile(
  filename: string,
  content: string,
  contentType: string,
): void {
  const blob = new Blob([content], { type: contentType });
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

function csvCell(value: string | number | null): string {
  let text = value === null ? "" : String(value);

  if (/^[=+\-@]/.test(text)) {
    text = `'${text}`;
  }

  return `"${text.replaceAll('"', '""')}"`;
}

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const textarea = document.createElement("textarea");

  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.append(textarea);
  textarea.select();

  try {
    if (!document.execCommand("copy")) {
      throw new Error("클립보드 복사를 지원하지 않는 브라우저입니다.");
    }
  } finally {
    textarea.remove();
  }
}

function detectionSummary(replay: FlightSessionReplay): Record<string, number> {
  const detections: Record<string, number> = {};

  for (const event of replay.aiEvents) {
    for (const detection of event.detections) {
      detections[detection.className] =
        (detections[detection.className] ?? 0) + 1;
    }
  }

  return detections;
}

export function FlightSessionComparison({
  initialLeftKey,
  initialRightKey,
}: FlightSessionComparisonProps) {
  const comparisonAbortRef = useRef<AbortController | null>(null);
  const [sessions, setSessions] = useState<DashboardFlightSessionItem[]>([]);
  const [leftKey, setLeftKey] = useState(initialLeftKey ?? "");
  const [rightKey, setRightKey] = useState(initialRightKey ?? "");
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evidenceMessage, setEvidenceMessage] = useState<string | null>(null);

  useEffect(() => {
    const abortController = new AbortController();

    fetch("/api/dashboard/operations?limit=20", {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: abortController.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(
            await readErrorMessage(
              response,
              `비행 세션 목록 조회 실패: ${response.status}`,
            ),
          );
        }

        const payload: unknown = await response.json();
        const candidates = extractComparableSessions(payload);

        if (candidates === null) {
          throw new Error("운영 대시보드 세션 응답 형식이 올바르지 않습니다.");
        }

        const requestedLeft = candidates.find(
          (session) => sessionKey(session) === initialLeftKey,
        );
        const selectedLeft = requestedLeft ?? candidates[0] ?? null;
        const requestedRight = candidates.find(
          (session) =>
            sessionKey(session) === initialRightKey &&
            sessionKey(session) !==
              (selectedLeft ? sessionKey(selectedLeft) : ""),
        );
        const selectedRight =
          requestedRight ??
          candidates.find(
            (session) =>
              sessionKey(session) !==
              (selectedLeft ? sessionKey(selectedLeft) : ""),
          ) ??
          null;

        setSessions(candidates);
        setLeftKey(selectedLeft ? sessionKey(selectedLeft) : "");
        setRightKey(selectedRight ? sessionKey(selectedRight) : "");
        setError(null);

        if (requestedLeft && requestedRight) {
          setComparisonLoading(true);
          comparisonAbortRef.current = abortController;

          const [left, right] = await Promise.all([
            loadReplay(requestedLeft, abortController.signal),
            loadReplay(requestedRight, abortController.signal),
          ]);

          setComparison({ left, right });
          window.history.replaceState(
            window.history.state,
            "",
            comparisonPath(
              sessionKey(requestedLeft),
              sessionKey(requestedRight),
            ),
          );
          setEvidenceMessage(
            "공유된 A/B 비교 결과를 자동으로 불러왔습니다.",
          );
        }
      })
      .catch((loadError: unknown) => {
        if (
          loadError instanceof DOMException &&
          loadError.name === "AbortError"
        ) {
          return;
        }

        setError(
          loadError instanceof Error
            ? loadError.message
            : "비교할 비행 세션을 불러오지 못했습니다.",
        );
      })
      .finally(() => {
        if (!abortController.signal.aborted) {
          setSessionsLoading(false);
          setComparisonLoading(false);
        }
      });

    return () => {
      abortController.abort();
      comparisonAbortRef.current?.abort();
    };
  }, [initialLeftKey, initialRightKey]);

  const leftSession = useMemo(
    () => sessions.find((session) => sessionKey(session) === leftKey) ?? null,
    [leftKey, sessions],
  );
  const rightSession = useMemo(
    () => sessions.find((session) => sessionKey(session) === rightKey) ?? null,
    [rightKey, sessions],
  );

  async function compareSessions() {
    if (!leftSession || !rightSession) {
      setError("비교할 두 비행 세션을 선택해 주세요.");
      return;
    }

    if (leftKey === rightKey) {
      setError("서로 다른 비행 세션을 선택해 주세요.");
      return;
    }

    comparisonAbortRef.current?.abort();
    const abortController = new AbortController();
    comparisonAbortRef.current = abortController;

    setComparisonLoading(true);
    setError(null);

    try {
      const [left, right] = await Promise.all([
        loadReplay(leftSession, abortController.signal),
        loadReplay(rightSession, abortController.signal),
      ]);

      setComparison({ left, right });
      window.history.replaceState(
        window.history.state,
        "",
        comparisonPath(leftKey, rightKey),
      );
      setEvidenceMessage(
        "비교 결과를 불러왔습니다. 현재 A/B 선택이 주소에 저장되었습니다.",
      );
    } catch (compareError) {
      if (
        compareError instanceof DOMException &&
        compareError.name === "AbortError"
      ) {
        return;
      }

      setComparison(null);
      setError(
        compareError instanceof Error
          ? compareError.message
          : "두 비행 세션을 비교하지 못했습니다.",
      );
    } finally {
      if (!abortController.signal.aborted) {
        setComparisonLoading(false);
      }
    }
  }

  const leftMetrics = comparison ? replayMetrics(comparison.left) : null;
  const rightMetrics = comparison ? replayMetrics(comparison.right) : null;

  const metricRows = useMemo<MetricRow[]>(() => {
    if (!comparison || !leftMetrics || !rightMetrics) {
      return [];
    }

    return [
      {
        label: "비행 시간",
        left: formatDuration(comparison.left.durationSeconds),
        right: formatDuration(comparison.right.durationSeconds),
        delta: signedNumber(
          comparison.right.durationSeconds - comparison.left.durationSeconds,
          "초",
        ),
      },
      {
        label: "이동 거리",
        left: formatDistance(leftMetrics.distanceMeters),
        right: formatDistance(rightMetrics.distanceMeters),
        delta: signedNumber(
          rightMetrics.distanceMeters - leftMetrics.distanceMeters,
          "m",
        ),
      },
      {
        label: "최대 고도",
        left:
          leftMetrics.maxAltitude === null
            ? "-"
            : `${leftMetrics.maxAltitude.toFixed(1)}m`,
        right:
          rightMetrics.maxAltitude === null
            ? "-"
            : `${rightMetrics.maxAltitude.toFixed(1)}m`,
        delta:
          leftMetrics.maxAltitude === null ||
          rightMetrics.maxAltitude === null
            ? "-"
            : signedNumber(
                rightMetrics.maxAltitude - leftMetrics.maxAltitude,
                "m",
                1,
              ),
      },
      {
        label: "저장 좌표",
        left: `${comparison.left.telemetryCount}개`,
        right: `${comparison.right.telemetryCount}개`,
        delta: signedNumber(
          comparison.right.telemetryCount - comparison.left.telemetryCount,
          "개",
        ),
      },
      {
        label: "AI 이벤트",
        left: `${comparison.left.aiEventCount}건`,
        right: `${comparison.right.aiEventCount}건`,
        delta: signedNumber(
          comparison.right.aiEventCount - comparison.left.aiEventCount,
          "건",
        ),
      },
      {
        label: "탐지 객체",
        left: `${comparison.left.detectionCount}개`,
        right: `${comparison.right.detectionCount}개`,
        delta: signedNumber(
          comparison.right.detectionCount - comparison.left.detectionCount,
          "개",
        ),
      },
      {
        label: "분당 탐지",
        left: `${leftMetrics.detectionsPerMinute.toFixed(1)}개`,
        right: `${rightMetrics.detectionsPerMinute.toFixed(1)}개`,
        delta: signedNumber(
          rightMetrics.detectionsPerMinute -
            leftMetrics.detectionsPerMinute,
          "개",
          1,
        ),
      },
      {
        label: "평균 추론",
        left:
          leftMetrics.averageInferenceMs === null
            ? "-"
            : `${leftMetrics.averageInferenceMs.toFixed(1)}ms`,
        right:
          rightMetrics.averageInferenceMs === null
            ? "-"
            : `${rightMetrics.averageInferenceMs.toFixed(1)}ms`,
        delta:
          leftMetrics.averageInferenceMs === null ||
          rightMetrics.averageInferenceMs === null
            ? "-"
            : signedNumber(
                rightMetrics.averageInferenceMs -
                  leftMetrics.averageInferenceMs,
                "ms",
                1,
              ),
      },
      {
        label: "배터리 소모",
        left:
          leftMetrics.batteryConsumption === null
            ? "-"
            : `${leftMetrics.batteryConsumption}%p`,
        right:
          rightMetrics.batteryConsumption === null
            ? "-"
            : `${rightMetrics.batteryConsumption}%p`,
        delta:
          leftMetrics.batteryConsumption === null ||
          rightMetrics.batteryConsumption === null
            ? "-"
            : signedNumber(
                rightMetrics.batteryConsumption -
                  leftMetrics.batteryConsumption,
                "%p",
              ),
      },
    ];
  }, [comparison, leftMetrics, rightMetrics]);

  function requireComparisonEvidence() {
    if (
      !comparison ||
      !leftSession ||
      !rightSession ||
      !leftMetrics ||
      !rightMetrics
    ) {
      throw new Error("먼저 서로 다른 두 비행을 비교해 주세요.");
    }

    return {
      comparison,
      leftSession,
      rightSession,
      leftMetrics,
      rightMetrics,
    };
  }

  function exportJson() {
    try {
      const evidence = requireComparisonEvidence();
      const payload = {
        schemaVersion: 1,
        project: "VisionFlow",
        evidenceType: "FLIGHT_SESSION_COMPARISON",
        generatedAt: new Date().toISOString(),
        comparisonUrl: new URL(
          comparisonPath(leftKey, rightKey),
          window.location.origin,
        ).toString(),
        deltaDefinition: "comparisonB - comparisonA",
        comparisonA: {
          selectionKey: leftKey,
          session: evidence.leftSession,
          calculatedMetrics: evidence.leftMetrics,
          detectionSummary: detectionSummary(evidence.comparison.left),
          replay: evidence.comparison.left,
        },
        comparisonB: {
          selectionKey: rightKey,
          session: evidence.rightSession,
          calculatedMetrics: evidence.rightMetrics,
          detectionSummary: detectionSummary(evidence.comparison.right),
          replay: evidence.comparison.right,
        },
        formattedMetrics: metricRows,
      };

      downloadTextFile(
        `${comparisonFileBase(
          evidence.leftSession,
          evidence.rightSession,
        )}.json`,
        `${JSON.stringify(payload, null, 2)}\n`,
        "application/json;charset=utf-8",
      );
      setEvidenceMessage("비교 원본과 계산 지표를 JSON으로 저장했습니다.");
      setError(null);
    } catch (exportError) {
      setError(
        exportError instanceof Error
          ? exportError.message
          : "비교 JSON을 저장하지 못했습니다.",
      );
    }
  }

  function exportCsv() {
    try {
      const evidence = requireComparisonEvidence();
      const rows = [
        ["VisionFlow 비행 성과 비교", "", "", ""],
        ["생성 시각", new Date().toISOString(), "", ""],
        [
          "비교 A",
          `${evidence.leftSession.name} (Drone #${evidence.leftSession.droneId})`,
          evidence.leftSession.sessionId,
          "",
        ],
        [
          "비교 B",
          `${evidence.rightSession.name} (Drone #${evidence.rightSession.droneId})`,
          evidence.rightSession.sessionId,
          "",
        ],
        ["", "", "", ""],
        ["지표", "비교 A", "비교 B", "B - A"],
        ...metricRows.map((row) => [
          row.label,
          row.left,
          row.right,
          row.delta,
        ]),
      ];
      const csv = rows
        .map((row) => row.map((value) => csvCell(value)).join(","))
        .join("\r\n");

      downloadTextFile(
        `${comparisonFileBase(
          evidence.leftSession,
          evidence.rightSession,
        )}.csv`,
        `\uFEFF${csv}\r\n`,
        "text/csv;charset=utf-8",
      );
      setEvidenceMessage("화면의 비교 지표를 CSV로 저장했습니다.");
      setError(null);
    } catch (exportError) {
      setError(
        exportError instanceof Error
          ? exportError.message
          : "비교 CSV를 저장하지 못했습니다.",
      );
    }
  }

  async function copyComparisonLink() {
    try {
      requireComparisonEvidence();
      const url = new URL(
        comparisonPath(leftKey, rightKey),
        window.location.origin,
      ).toString();

      await copyText(url);
      setEvidenceMessage("현재 A/B 비교 링크를 클립보드에 복사했습니다.");
      setError(null);
    } catch (copyError) {
      setError(
        copyError instanceof Error
          ? copyError.message
          : "비교 링크를 복사하지 못했습니다.",
      );
    }
  }

  return (
    <main className="min-h-screen bg-slate-100 px-4 py-8 print:bg-white print:px-0 print:py-0">
      <section className="mx-auto max-w-6xl">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold uppercase tracking-[0.18em] text-cyan-700">
              Flight Analytics
            </p>
            <h1 className="mt-2 text-3xl font-black text-slate-950">
              비행 성과 비교 분석
            </h1>
            <p className="mt-2 text-sm text-slate-600">
              최근 완료·중단 세션 두 개의 운항 지표와 AI 탐지 결과를 비교합니다.
            </p>
          </div>
          <Link
            href="/dashboard"
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700 print:hidden"
          >
            운영 대시보드
          </Link>
        </div>

        <article className="mt-6 rounded-2xl border border-cyan-200 bg-white p-5 shadow-sm print:hidden">
          <div className="grid gap-4 lg:grid-cols-[1fr_auto_1fr] lg:items-end">
            <SessionSelector
              id="left-flight-session"
              label="비교 A"
              value={leftKey}
              sessions={sessions}
              disabled={sessionsLoading || comparisonLoading}
              onChange={(value) => {
                setLeftKey(value);
                setComparison(null);
                setEvidenceMessage(null);
              }}
            />
            <div className="hidden pb-3 text-center text-xl font-black text-slate-400 lg:block">
              VS
            </div>
            <SessionSelector
              id="right-flight-session"
              label="비교 B"
              value={rightKey}
              sessions={sessions}
              disabled={sessionsLoading || comparisonLoading}
              onChange={(value) => {
                setRightKey(value);
                setComparison(null);
                setEvidenceMessage(null);
              }}
            />
          </div>

          <button
            type="button"
            onClick={() => void compareSessions()}
            disabled={
              sessionsLoading ||
              comparisonLoading ||
              !leftSession ||
              !rightSession
            }
            className="mt-4 w-full rounded-xl bg-cyan-800 px-5 py-3 font-black text-white transition hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {comparisonLoading ? "비교 데이터 조회 중" : "두 비행 비교"}
          </button>

          {!sessionsLoading && sessions.length < 2 && (
            <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
              비교하려면 완료 또는 중단된 비행 세션이 두 개 이상 필요합니다.
            </div>
          )}

          {error && (
            <div
              role="alert"
              className="mt-4 rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-900"
            >
              {error}
            </div>
          )}
        </article>

        {comparison &&
          leftSession &&
          rightSession &&
          leftMetrics &&
          rightMetrics && (
            <div className="mt-6 space-y-5">
              <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm print:hidden">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="font-black text-slate-950">
                      비교 결과 증적
                    </h2>
                    <p className="mt-1 text-xs text-slate-500">
                      동일 비교를 다시 열거나 발표·제출용 파일로 저장합니다.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void copyComparisonLink()}
                      className="rounded-lg border border-cyan-300 bg-cyan-50 px-3 py-2 text-xs font-black text-cyan-900"
                    >
                      비교 링크 복사
                    </button>
                    <button
                      type="button"
                      onClick={exportJson}
                      className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-black text-slate-800"
                    >
                      JSON 저장
                    </button>
                    <button
                      type="button"
                      onClick={exportCsv}
                      className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-black text-slate-800"
                    >
                      CSV 저장
                    </button>
                    <button
                      type="button"
                      onClick={() => window.print()}
                      className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-black text-white"
                    >
                      인쇄 / PDF
                    </button>
                  </div>
                </div>
                {evidenceMessage && (
                  <p
                    role="status"
                    aria-live="polite"
                    className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-800"
                  >
                    {evidenceMessage}
                  </p>
                )}
              </article>

              <div className="grid gap-4 lg:grid-cols-2">
                <SessionOverview
                  label="비교 A"
                  session={leftSession}
                  replay={comparison.left}
                />
                <SessionOverview
                  label="비교 B"
                  session={rightSession}
                  replay={comparison.right}
                />
              </div>

              <article className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                <div className="border-b border-slate-200 p-5">
                  <h2 className="text-lg font-black text-slate-950">
                    지표 비교
                  </h2>
                  <p className="mt-1 text-xs text-slate-500">
                    차이는 비교 B에서 비교 A를 뺀 값입니다.
                  </p>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px] border-collapse text-sm">
                    <thead>
                      <tr className="bg-slate-50 text-left text-slate-600">
                        <th className="border-b border-slate-200 p-3">지표</th>
                        <th className="border-b border-slate-200 p-3">비교 A</th>
                        <th className="border-b border-slate-200 p-3">비교 B</th>
                        <th className="border-b border-slate-200 p-3">
                          B - A
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {metricRows.map((row) => (
                        <tr key={row.label}>
                          <th className="border-b border-slate-100 p-3 text-left text-slate-700">
                            {row.label}
                          </th>
                          <td className="border-b border-slate-100 p-3 font-semibold text-slate-950">
                            {row.left}
                          </td>
                          <td className="border-b border-slate-100 p-3 font-semibold text-slate-950">
                            {row.right}
                          </td>
                          <td className="border-b border-slate-100 p-3 font-bold text-cyan-800">
                            {row.delta}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </article>

              <div className="grid gap-5 lg:grid-cols-2">
                <ComparisonBars
                  title="이동 거리"
                  leftValue={leftMetrics.distanceMeters}
                  rightValue={rightMetrics.distanceMeters}
                  formatter={formatDistance}
                />
                <ComparisonBars
                  title="탐지 객체"
                  leftValue={comparison.left.detectionCount}
                  rightValue={comparison.right.detectionCount}
                  formatter={(value) => `${Math.round(value)}개`}
                />
              </div>

              <div className="grid gap-5 lg:grid-cols-2">
                <DetectionSummary
                  label="비교 A 탐지 구성"
                  replay={comparison.left}
                />
                <DetectionSummary
                  label="비교 B 탐지 구성"
                  replay={comparison.right}
                />
              </div>
            </div>
          )}
      </section>
    </main>
  );
}

function SessionSelector({
  id,
  label,
  value,
  sessions,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  sessions: DashboardFlightSessionItem[];
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label htmlFor={id} className="text-sm font-bold text-slate-800">
      {label}
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-3 py-3 font-normal text-slate-900 disabled:opacity-60"
      >
        <option value="">비행 세션 선택</option>
        {sessions.map((session) => (
          <option key={sessionKey(session)} value={sessionKey(session)}>
            Drone #{session.droneId} · {session.name} ·{" "}
            {formatDateTime(session.endedAt ?? session.startedAt)}
          </option>
        ))}
      </select>
    </label>
  );
}

function SessionOverview({
  label,
  session,
  replay,
}: {
  label: string;
  session: DashboardFlightSessionItem;
  replay: FlightSessionReplay;
}) {
  const snapshot = replay.aiEvents.find((event) => event.snapshotAvailable);

  return (
    <article className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      {snapshot && (
        <div className="bg-slate-950">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={
              snapshot.snapshotUrl ??
              `/api/ai/events/${snapshot.id}/snapshot`
            }
            alt={`${label} 대표 탐지`}
            className="aspect-video w-full object-contain"
          />
        </div>
      )}
      <div className="p-5">
        <span className="rounded-full bg-cyan-100 px-3 py-1 text-xs font-black text-cyan-800">
          {label}
        </span>
        <h2 className="mt-3 text-lg font-black text-slate-950">
          {session.name}
        </h2>
        <div className="mt-1 text-sm text-slate-500">
          Drone #{session.droneId} · {formatDateTime(replay.startedAt)}
        </div>
        <div className="mt-4 flex flex-wrap gap-2 print:hidden">
          <Link
            href={reportHref(session)}
            className="rounded-lg bg-violet-700 px-3 py-2 text-xs font-bold text-white"
          >
            종합 보고서
          </Link>
          <Link
            href={replayHref(session)}
            className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white"
          >
            관제 리플레이
          </Link>
        </div>
      </div>
    </article>
  );
}

function ComparisonBars({
  title,
  leftValue,
  rightValue,
  formatter,
}: {
  title: string;
  leftValue: number;
  rightValue: number;
  formatter: (value: number) => string;
}) {
  const maximum = Math.max(leftValue, rightValue, 1);

  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="font-black text-slate-950">{title}</h2>
      <div className="mt-4 space-y-4">
        <ComparisonBar
          label="비교 A"
          value={leftValue}
          maximum={maximum}
          formattedValue={formatter(leftValue)}
          className="bg-cyan-600"
        />
        <ComparisonBar
          label="비교 B"
          value={rightValue}
          maximum={maximum}
          formattedValue={formatter(rightValue)}
          className="bg-violet-600"
        />
      </div>
    </article>
  );
}

function ComparisonBar({
  label,
  value,
  maximum,
  formattedValue,
  className,
}: {
  label: string;
  value: number;
  maximum: number;
  formattedValue: string;
  className: string;
}) {
  const width = `${Math.max(0, Math.min(100, (value / maximum) * 100))}%`;

  return (
    <div>
      <div className="flex justify-between text-xs font-bold text-slate-600">
        <span>{label}</span>
        <span>{formattedValue}</span>
      </div>
      <div className="mt-2 h-3 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${className}`} style={{ width }} />
      </div>
    </div>
  );
}

function DetectionSummary({
  label,
  replay,
}: {
  label: string;
  replay: FlightSessionReplay;
}) {
  const detections = new Map<string, number>();

  for (const event of replay.aiEvents) {
    for (const detection of event.detections) {
      detections.set(
        detection.className,
        (detections.get(detection.className) ?? 0) + 1,
      );
    }
  }

  const entries = Array.from(detections.entries()).sort(
    ([firstName, firstCount], [secondName, secondCount]) =>
      secondCount - firstCount || firstName.localeCompare(secondName),
  );

  return (
    <article className="rounded-2xl border border-violet-200 bg-white p-5 shadow-sm">
      <h2 className="font-black text-violet-950">{label}</h2>
      <div className="mt-4 flex flex-wrap gap-2">
        {entries.length > 0 ? (
          entries.map(([className, count]) => (
            <span
              key={className}
              className="rounded-full bg-violet-100 px-3 py-1 text-sm font-bold text-violet-800"
            >
              {className} {count}개
            </span>
          ))
        ) : (
          <span className="text-sm text-slate-500">탐지 객체 없음</span>
        )}
      </div>
    </article>
  );
}
