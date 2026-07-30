"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useOperatorAccess } from "@/components/security/operator-access-provider";
import type { DroneTrackPoint } from "@/hooks/use-drone-fleet-telemetry";
import type { AiInferenceEvent } from "@/types/ai-inference-event";
import type {
  FlightReplayTelemetry,
  FlightSessionReplay,
  FlightSessionSummary,
} from "@/types/flight-session-replay";

interface FlightSessionReplayPanelProps {
  droneId: number;
  initialSessionId?: string | null;
  currentTimeMs: number | null;
  onReplayLoaded: (
    replay: FlightSessionReplay,
    points: DroneTrackPoint[],
  ) => void;
}

const EVENT_SYNC_WINDOW_MS = 5_000;

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
  const minutes = Math.floor(safeSeconds / 60);
  const seconds = safeSeconds % 60;

  return `${minutes}분 ${seconds}초`;
}

function isSessionStatus(
  value: unknown,
): value is FlightSessionSummary["status"] {
  return (
    value === "READY" ||
    value === "ACTIVE" ||
    value === "COMPLETED" ||
    value === "ABORTED" ||
    value === "LEGACY"
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

function telemetryToTrackPoint(
  telemetry: FlightReplayTelemetry,
): DroneTrackPoint | null {
  if (telemetry.latitude === null || telemetry.longitude === null) {
    return null;
  }

  const latitude = Number(telemetry.latitude);
  const longitude = Number(telemetry.longitude);
  const altitude =
    telemetry.altitude === null ? null : Number(telemetry.altitude);
  const heading =
    telemetry.heading === null ? null : Number(telemetry.heading);
  const receivedAt = parseDateTime(telemetry.recordedAt);

  if (
    !Number.isFinite(latitude) ||
    !Number.isFinite(longitude) ||
    !Number.isFinite(receivedAt)
  ) {
    return null;
  }

  return {
    latitude,
    longitude,
    altitude: altitude !== null && Number.isFinite(altitude) ? altitude : null,
    heading: heading !== null && Number.isFinite(heading) ? heading : null,
    receivedAt,
  };
}

async function readErrorMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const payload: unknown = await response.json();

    if (typeof payload === "object" && payload !== null) {
      const candidate = payload as { message?: unknown; detail?: unknown };

      if (typeof candidate.message === "string") {
        return candidate.message;
      }

      if (typeof candidate.detail === "string") {
        return candidate.detail;
      }
    }
  } catch {
    return fallback;
  }

  return fallback;
}

async function requestSessionSummaries(
  droneId: number,
  query: string,
  signal: AbortSignal,
): Promise<FlightSessionSummary[]> {
  const searchParams = new URLSearchParams({ limit: "20" });

  if (query) {
    searchParams.set("query", query);
  }

  const response = await fetch(
    `/api/drones/${droneId}/flight-sessions?${searchParams}`,
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
        `비행 세션 목록 조회 실패: ${response.status}`,
      ),
    );
  }

  const payload: unknown = await response.json();

  if (!Array.isArray(payload) || !payload.every(isSessionSummary)) {
    throw new Error("비행 세션 목록 응답 형식이 올바르지 않습니다.");
  }

  if (payload.some((session) => session.droneId !== droneId)) {
    throw new Error("선택한 드론과 다른 세션이 목록에 포함되어 있습니다.");
  }

  return payload;
}

function eventTimestamp(event: AiInferenceEvent): number {
  return parseDateTime(event.capturedAt);
}

function eventClassNames(event: AiInferenceEvent): string {
  const names = Array.from(
    new Set(event.detections.map((detection) => detection.className)),
  );

  return names.length > 0 ? names.join(", ") : "탐지 상세 없음";
}

function csvCell(value: string | number | null): string {
  if (value === null) {
    return '""';
  }

  const rawValue = String(value);
  const spreadsheetSafeValue = /^[=+\-@]/.test(rawValue)
    ? `'${rawValue}`
    : rawValue;

  return `"${spreadsheetSafeValue.replaceAll('"', '""')}"`;
}

function telemetryCsv(telemetry: FlightReplayTelemetry[]): string {
  const headers = [
    "recordedAt",
    "droneId",
    "flightSessionId",
    "telemetrySource",
    "sourceDeviceId",
    "status",
    "latitude",
    "longitude",
    "altitude",
    "batteryLevel",
    "heading",
    "pitch",
    "roll",
    "groundSpeed",
    "horizontalAccuracy",
    "verticalAccuracy",
  ];
  const rows = telemetry.map((point) =>
    [
      point.recordedAt,
      point.droneId,
      point.flightSessionId,
      point.telemetrySource,
      point.sourceDeviceId,
      point.status,
      point.latitude,
      point.longitude,
      point.altitude,
      point.batteryLevel,
      point.heading,
      point.pitch,
      point.roll,
      point.groundSpeed,
      point.horizontalAccuracy,
      point.verticalAccuracy,
    ]
      .map(csvCell)
      .join(","),
  );

  return `\uFEFF${[headers.map(csvCell).join(","), ...rows].join("\r\n")}`;
}

function downloadTextFile(
  fileName: string,
  contents: string,
  mimeType: string,
): void {
  const blob = new Blob([contents], { type: mimeType });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = objectUrl;
  link.download = fileName;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}

async function copyTextToClipboard(value: string): Promise<void> {
  if (window.isSecureContext && navigator.clipboard) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const textArea = document.createElement("textarea");
  textArea.value = value;
  textArea.setAttribute("readonly", "");
  textArea.style.position = "fixed";
  textArea.style.opacity = "0";
  document.body.append(textArea);
  textArea.select();

  const copied = document.execCommand("copy");
  textArea.remove();

  if (!copied) {
    throw new Error("클립보드 복사를 지원하지 않는 브라우저입니다.");
  }
}

export function FlightSessionReplayPanel({
  droneId,
  initialSessionId = null,
  currentTimeMs,
  onReplayLoaded,
}: FlightSessionReplayPanelProps) {
  const { canOperate, operateDeniedReason } = useOperatorAccess();
  const sessionListAbortRef = useRef<AbortController | null>(null);
  const replayAbortRef = useRef<AbortController | null>(null);
  const sessionUpdateAbortRef = useRef<AbortController | null>(null);
  const onReplayLoadedRef = useRef(onReplayLoaded);
  const [sessions, setSessions] = useState<FlightSessionSummary[]>([]);
  const [sessionSearch, setSessionSearch] = useState("");
  const [sessionId, setSessionId] = useState(() => {
    const normalizedSessionId = initialSessionId?.trim() ?? "";

    return normalizedSessionId.length <= 36 ? normalizedSessionId : "";
  });
  const [replay, setReplay] = useState<FlightSessionReplay | null>(null);
  const [sessionListLoading, setSessionListLoading] = useState(true);
  const [sessionListError, setSessionListError] = useState<string | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [sessionUpdateLoading, setSessionUpdateLoading] = useState(false);
  const [sessionUpdateError, setSessionUpdateError] = useState<string | null>(
    null,
  );
  const [evidenceMessage, setEvidenceMessage] = useState<string | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  useEffect(() => {
    onReplayLoadedRef.current = onReplayLoaded;
  }, [onReplayLoaded]);

  const loadSessionList = useCallback(
    async (rawQuery: string) => {
      const normalizedQuery = rawQuery.trim();

      if (normalizedQuery.length > 36) {
        setSessionListError("세션 검색어는 36자 이하여야 합니다.");
        return;
      }

      sessionListAbortRef.current?.abort();
      const abortController = new AbortController();
      sessionListAbortRef.current = abortController;

      setSessionListLoading(true);
      setSessionListError(null);

      try {
        const nextSessions = await requestSessionSummaries(
          droneId,
          normalizedQuery,
          abortController.signal,
        );

        setSessions(nextSessions);
      } catch (loadError) {
        if (
          loadError instanceof DOMException &&
          loadError.name === "AbortError"
        ) {
          return;
        }

        setSessions([]);
        setSessionListError(
          loadError instanceof Error
            ? loadError.message
            : "비행 세션 목록을 불러오지 못했습니다.",
        );
      } finally {
        if (!abortController.signal.aborted) {
          setSessionListLoading(false);
        }
      }
    },
    [droneId],
  );

  useEffect(() => {
    const abortController = new AbortController();
    sessionListAbortRef.current = abortController;

    requestSessionSummaries(droneId, "", abortController.signal)
      .then((nextSessions) => {
        setSessions(nextSessions);
        setSessionListError(null);
      })
      .catch((loadError: unknown) => {
        if (
          loadError instanceof DOMException &&
          loadError.name === "AbortError"
        ) {
          return;
        }

        setSessions([]);
        setSessionListError(
          loadError instanceof Error
            ? loadError.message
            : "비행 세션 목록을 불러오지 못했습니다.",
        );
      })
      .finally(() => {
        if (!abortController.signal.aborted) {
          setSessionListLoading(false);
        }
      });

    return () => {
      abortController.abort();
      replayAbortRef.current?.abort();
      sessionUpdateAbortRef.current?.abort();
    };
  }, [droneId]);

  const activeEvent = useMemo(() => {
    if (!replay || currentTimeMs === null) {
      return null;
    }

    let nearest: AiInferenceEvent | null = null;
    let nearestDistance = Number.POSITIVE_INFINITY;

    for (const event of replay.aiEvents) {
      const timestamp = eventTimestamp(event);

      if (!Number.isFinite(timestamp)) {
        continue;
      }

      const distance = Math.abs(timestamp - currentTimeMs);

      if (distance <= EVENT_SYNC_WINDOW_MS && distance < nearestDistance) {
        nearest = event;
        nearestDistance = distance;
      }
    }

    return nearest;
  }, [currentTimeMs, replay]);

  const passedEvents = useMemo(() => {
    if (!replay) {
      return [];
    }

    if (currentTimeMs === null) {
      return replay.aiEvents.slice(0, 5);
    }

    return replay.aiEvents
      .filter((event) => eventTimestamp(event) <= currentTimeMs)
      .slice(-5)
      .reverse();
  }, [currentTimeMs, replay]);

  const loadReplay = useCallback(async (requestedSessionId: string) => {
    const normalizedSessionId = requestedSessionId.trim();

    if (!normalizedSessionId || normalizedSessionId.length > 36) {
      setError("비행 세션 UUID를 1~36자로 입력해 주세요.");
      return;
    }

    setSessionId(normalizedSessionId);
    replayAbortRef.current?.abort();
    const abortController = new AbortController();
    replayAbortRef.current = abortController;

    setReplayLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/drones/${droneId}/flight-sessions/` +
          `${encodeURIComponent(normalizedSessionId)}/replay` +
          "?telemetryLimit=5000&eventLimit=1000",
        {
          method: "GET",
          headers: { Accept: "application/json" },
          cache: "no-store",
          signal: abortController.signal,
        },
      );

      if (!response.ok) {
        throw new Error(
          await readErrorMessage(
            response,
            `통합 리플레이 조회 실패: ${response.status}`,
          ),
        );
      }

      const payload: unknown = await response.json();

      if (!isReplayResponse(payload)) {
        throw new Error("통합 리플레이 응답 형식이 올바르지 않습니다.");
      }

      if (payload.droneId !== droneId) {
        throw new Error("선택한 드론과 세션의 드론 ID가 다릅니다.");
      }

      const points = payload.telemetry
        .map(telemetryToTrackPoint)
        .filter((point): point is DroneTrackPoint => point !== null);

      if (points.length === 0) {
        throw new Error("이 세션에는 지도에서 재생할 좌표가 없습니다.");
      }

      setReplay(payload);
      setEvidenceMessage(null);
      setEvidenceError(null);
      onReplayLoadedRef.current(payload, points);
    } catch (loadError) {
      if (
        loadError instanceof DOMException &&
        loadError.name === "AbortError"
      ) {
        return;
      }

      setReplay(null);
      setError(
        loadError instanceof Error
          ? loadError.message
          : "통합 리플레이를 불러오지 못했습니다.",
      );
    } finally {
      if (!abortController.signal.aborted) {
        setReplayLoading(false);
      }
    }
  }, [droneId]);

  useEffect(() => {
    const normalizedSessionId = initialSessionId?.trim() ?? "";

    if (!normalizedSessionId || normalizedSessionId.length > 36) {
      return;
    }

    const timerId = window.setTimeout(() => {
      void loadReplay(normalizedSessionId);
    }, 0);

    return () => {
      window.clearTimeout(timerId);
      replayAbortRef.current?.abort();
    };
  }, [initialSessionId, loadReplay]);

  function replayFileBaseName(loadedReplay: FlightSessionReplay): string {
    const safeSessionId = loadedReplay.sessionId.replace(
      /[^a-zA-Z0-9_-]/g,
      "_",
    );

    return `visionflow-flight-${loadedReplay.droneId}-${safeSessionId}`;
  }

  function downloadReplayJson() {
    if (!replay) {
      return;
    }

    const evidence = {
      schemaVersion: 1,
      exportedAt: new Date().toISOString(),
      project: "VisionFlow",
      type: "FLIGHT_SESSION_REPLAY",
      replay,
    };

    downloadTextFile(
      `${replayFileBaseName(replay)}-replay.json`,
      `${JSON.stringify(evidence, null, 2)}\n`,
      "application/json;charset=utf-8",
    );
    setEvidenceError(null);
    setEvidenceMessage("통합 리플레이 JSON을 다운로드했습니다.");
  }

  function downloadTelemetryCsv() {
    if (!replay) {
      return;
    }

    downloadTextFile(
      `${replayFileBaseName(replay)}-telemetry.csv`,
      telemetryCsv(replay.telemetry),
      "text/csv;charset=utf-8",
    );
    setEvidenceError(null);
    setEvidenceMessage(
      `텔레메트리 ${replay.telemetry.length}개를 CSV로 다운로드했습니다.`,
    );
  }

  async function copyReplayLink() {
    if (!replay) {
      return;
    }

    const replayUrl = new URL("/drones", window.location.origin);
    replayUrl.searchParams.set("droneId", String(replay.droneId));
    replayUrl.searchParams.set("sessionId", replay.sessionId);
    replayUrl.hash = "flight-session-replay";

    try {
      await copyTextToClipboard(replayUrl.toString());
      setEvidenceError(null);
      setEvidenceMessage("이 비행 세션의 관제 리플레이 링크를 복사했습니다.");
    } catch (copyError) {
      setEvidenceMessage(null);
      setEvidenceError(
        copyError instanceof Error
          ? copyError.message
          : "관제 리플레이 링크를 복사하지 못했습니다.",
      );
    }
  }

  function beginSessionEdit(session: FlightSessionSummary) {
    if (!session.managed || !canOperate) {
      if (!canOperate) {
        setSessionUpdateError(operateDeniedReason);
      }
      return;
    }

    setEditingSessionId(session.sessionId);
    setEditName(session.name);
    setEditDescription(session.description ?? "");
    setSessionUpdateError(null);
  }

  function cancelSessionEdit() {
    setEditingSessionId(null);
    setEditName("");
    setEditDescription("");
    setSessionUpdateError(null);
  }

  async function saveSessionMetadata() {
    if (!canOperate) {
      setSessionUpdateError(operateDeniedReason);
      return;
    }

    if (!editingSessionId) {
      return;
    }

    const normalizedName = editName.trim();

    if (!normalizedName) {
      setSessionUpdateError("비행 세션명을 입력해 주세요.");
      return;
    }

    if (normalizedName.length > 120) {
      setSessionUpdateError("비행 세션명은 120자 이하여야 합니다.");
      return;
    }

    if (editDescription.length > 500) {
      setSessionUpdateError("비행 세션 설명은 500자 이하여야 합니다.");
      return;
    }

    sessionUpdateAbortRef.current?.abort();
    const abortController = new AbortController();
    sessionUpdateAbortRef.current = abortController;

    setSessionUpdateLoading(true);
    setSessionUpdateError(null);

    try {
      const response = await fetch(
        `/api/drones/${droneId}/flight-sessions/` +
          encodeURIComponent(editingSessionId),
        {
          method: "PATCH",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            name: normalizedName,
            description: editDescription,
          }),
          cache: "no-store",
          signal: abortController.signal,
        },
      );

      if (!response.ok) {
        throw new Error(
          await readErrorMessage(
            response,
            `비행 세션 정보 수정 실패: ${response.status}`,
          ),
        );
      }

      setEditingSessionId(null);
      setEditName("");
      setEditDescription("");
      await loadSessionList(sessionSearch);
    } catch (updateError) {
      if (
        updateError instanceof DOMException &&
        updateError.name === "AbortError"
      ) {
        return;
      }

      setSessionUpdateError(
        updateError instanceof Error
          ? updateError.message
          : "비행 세션 정보를 수정하지 못했습니다.",
      );
    } finally {
      if (!abortController.signal.aborted) {
        setSessionUpdateLoading(false);
      }
    }
  }

  return (
    <section
      id="flight-session-replay"
      className="scroll-mt-6 rounded-2xl border border-cyan-200 bg-cyan-50 p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-bold text-cyan-950">통합 비행 세션 리플레이</h3>
          <p className="mt-1 text-sm text-cyan-800">
            텔레메트리 경로와 같은 시각의 YOLO 탐지 이벤트를 함께 재생합니다.
          </p>
        </div>

        {replay && (
          <div className="flex flex-wrap items-center justify-end gap-2">
            <span className="rounded-full bg-cyan-700 px-3 py-1 text-xs font-bold text-white">
              SESSION LOADED
            </span>
            <Link
              href={
                `/drones/${replay.droneId}/flight-sessions/` +
                `${encodeURIComponent(replay.sessionId)}/report`
              }
              className="rounded-lg bg-violet-700 px-3 py-2 text-xs font-bold text-white transition hover:bg-violet-600"
            >
              종합 보고서
            </Link>
            <button
              type="button"
              onClick={downloadReplayJson}
              className="rounded-lg border border-cyan-300 bg-white px-3 py-2 text-xs font-bold text-cyan-900 transition hover:bg-cyan-100"
            >
              리플레이 JSON
            </button>
            <button
              type="button"
              onClick={downloadTelemetryCsv}
              className="rounded-lg border border-cyan-300 bg-white px-3 py-2 text-xs font-bold text-cyan-900 transition hover:bg-cyan-100"
            >
              텔레메트리 CSV
            </button>
            <button
              type="button"
              onClick={() => void copyReplayLink()}
              className="rounded-lg bg-cyan-800 px-3 py-2 text-xs font-bold text-white transition hover:bg-cyan-700"
            >
              리플레이 링크 복사
            </button>
          </div>
        )}
      </div>

      {evidenceMessage && (
        <div
          role="status"
          className="mt-3 rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm font-semibold text-emerald-800"
        >
          {evidenceMessage}
        </div>
      )}

      {evidenceError && (
        <div
          role="alert"
          className="mt-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm font-semibold text-red-800"
        >
          {evidenceError}
        </div>
      )}

      <div className="mt-4 rounded-xl border border-cyan-200 bg-white p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="font-bold text-slate-900">최근 비행 세션</div>
            <div className="mt-0.5 text-xs text-slate-500">
              경로가 있는 카드를 누르면 즉시 지도 리플레이를 불러옵니다.
            </div>
          </div>
          <span className="text-xs font-semibold text-slate-500">
            최대 20개
          </span>
        </div>

        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <label className="sr-only" htmlFor={`flight-session-search-${droneId}`}>
            비행 세션 UUID 검색
          </label>
          <input
            id={`flight-session-search-${droneId}`}
            type="search"
            value={sessionSearch}
            maxLength={36}
            placeholder="UUID 전체 또는 일부 검색"
            onChange={(event) => setSessionSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void loadSessionList(sessionSearch);
              }
            }}
            className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm"
          />
          <button
            type="button"
            onClick={() => void loadSessionList(sessionSearch)}
            disabled={sessionListLoading}
            className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {sessionListLoading ? "조회 중" : "검색"}
          </button>
          <button
            type="button"
            onClick={() => {
              setSessionSearch("");
              void loadSessionList("");
            }}
            disabled={sessionListLoading}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            새로고침
          </button>
        </div>

        {sessionListError && (
          <div className="mt-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
            {sessionListError}
          </div>
        )}

        {!sessionListLoading && !sessionListError && sessions.length === 0 && (
          <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-500">
            조회된 비행 세션이 없습니다. /mobile-flight에서 같은 UUID로
            텔레메트리 또는 영상을 전송한 뒤 새로고침하세요.
          </div>
        )}

        {sessions.length > 0 && (
          <div className="mt-3 grid gap-2 lg:grid-cols-2">
            {sessions.map((session) => {
              const selected = sessionId === session.sessionId;
              const replayDisabled = !session.hasTelemetry || replayLoading;
              const reportAvailable =
                session.hasTelemetry &&
                (session.status === "COMPLETED" ||
                  session.status === "ABORTED");

              return (
                <div
                  key={session.sessionId}
                  className={`overflow-hidden rounded-xl border transition ${
                    selected
                      ? "border-cyan-500 ring-2 ring-cyan-200"
                      : "border-slate-200"
                  }`}
                >
                  <button
                    type="button"
                    disabled={replayDisabled}
                    aria-pressed={selected}
                    title={
                      session.hasTelemetry
                        ? "이 세션을 지도에서 재생"
                        : "저장된 텔레메트리 경로가 없는 세션"
                    }
                    onClick={() => void loadReplay(session.sessionId)}
                    className={`w-full p-3 text-left transition ${
                      selected
                        ? "bg-cyan-50"
                        : "bg-white hover:bg-cyan-50/50"
                    } disabled:cursor-not-allowed disabled:opacity-60`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <SessionStatusBadge status={session.status} />
                          <span className="text-xs font-semibold text-slate-500">
                            {formatDateTime(session.endedAt)}
                          </span>
                        </div>
                        <div className="mt-2 break-words font-bold text-slate-950">
                          {session.name}
                        </div>
                        {session.description && (
                          <div className="mt-1 break-words text-xs text-slate-600">
                            {session.description}
                          </div>
                        )}
                        <div className="mt-2 break-all font-mono text-[11px] text-slate-500">
                          {session.sessionId}
                        </div>
                      </div>
                      {selected && (
                        <span className="shrink-0 rounded-full bg-cyan-700 px-2 py-1 text-[10px] font-bold text-white">
                          선택됨
                        </span>
                      )}
                    </div>

                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600 sm:grid-cols-4">
                      <span>비행 {formatDuration(session.durationSeconds)}</span>
                      <span>좌표 {session.telemetryCount}개</span>
                      <span>AI {session.aiEventCount}건</span>
                      <span>탐지 {session.detectionCount}개</span>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-1">
                      <SessionBadge
                        enabled={session.hasTelemetry}
                        enabledLabel="경로 있음"
                        disabledLabel="경로 없음"
                      />
                      <SessionBadge
                        enabled={session.hasAiEvents}
                        enabledLabel="AI 이벤트 있음"
                        disabledLabel="AI 이벤트 없음"
                      />
                    </div>
                  </button>

                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-3 py-2">
                    <span className="min-w-0 truncate text-[11px] font-semibold text-slate-500">
                      {session.managed
                        ? session.sourceDeviceId || "서버 관리 세션"
                        : "LEGACY · 읽기 전용"}
                    </span>
                    <div className="flex flex-wrap items-center justify-end gap-2">
                      {reportAvailable && (
                        <Link
                          href={
                            `/drones/${session.droneId}/flight-sessions/` +
                            `${encodeURIComponent(session.sessionId)}/report`
                          }
                          className="shrink-0 rounded-md bg-violet-700 px-2.5 py-1 text-xs font-bold text-white transition hover:bg-violet-600"
                        >
                          종합 보고서
                        </Link>
                      )}
                      <button
                        type="button"
                        onClick={() => beginSessionEdit(session)}
                        disabled={
                          !session.managed ||
                          sessionUpdateLoading ||
                          !canOperate
                        }
                        title={
                          !canOperate
                            ? operateDeniedReason ?? undefined
                            : !session.managed
                              ? "LEGACY 세션은 읽기 전용입니다."
                              : undefined
                        }
                        className="shrink-0 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-bold text-slate-700 hover:border-cyan-400 hover:text-cyan-800 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        세션 정보 수정
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {editingSessionId && (
          <div className="mt-3 rounded-xl border border-blue-300 bg-blue-50 p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <div className="font-bold text-blue-950">비행 세션 정보 수정</div>
                <div className="mt-1 break-all font-mono text-[11px] text-blue-700">
                  {editingSessionId}
                </div>
              </div>
              <span className="text-xs font-semibold text-blue-700">
                이름 120자 · 설명 500자
              </span>
            </div>

            <div className="mt-3 grid gap-3">
              <label className="text-sm font-semibold text-slate-800">
                세션명
                <input
                  type="text"
                  value={editName}
                  maxLength={120}
                  disabled={sessionUpdateLoading}
                  onChange={(event) => setEditName(event.target.value)}
                  className="mt-1 block w-full rounded-lg border border-blue-200 bg-white px-3 py-2 font-normal text-slate-900 disabled:opacity-60"
                />
              </label>

              <label className="text-sm font-semibold text-slate-800">
                설명
                <textarea
                  value={editDescription}
                  maxLength={500}
                  rows={3}
                  disabled={sessionUpdateLoading}
                  placeholder="선택 사항"
                  onChange={(event) => setEditDescription(event.target.value)}
                  className="mt-1 block w-full resize-y rounded-lg border border-blue-200 bg-white px-3 py-2 font-normal text-slate-900 disabled:opacity-60"
                />
              </label>
            </div>

            {sessionUpdateError && (
              <div className="mt-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
                {sessionUpdateError}
              </div>
            )}

            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                onClick={cancelSessionEdit}
                disabled={sessionUpdateLoading}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                취소
              </button>
              <button
                type="button"
                onClick={() => void saveSessionMetadata()}
                disabled={sessionUpdateLoading || !canOperate}
                title={canOperate ? undefined : operateDeniedReason ?? undefined}
                className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {sessionUpdateLoading ? "저장 중" : "저장"}
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="mt-3 rounded-xl border border-cyan-200 bg-cyan-100/40 p-3">
        <div className="text-xs font-bold text-cyan-950">
          UUID 직접 입력 (보조)
        </div>
        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <label className="sr-only" htmlFor={`flight-session-id-${droneId}`}>
            직접 불러올 비행 세션 UUID
          </label>
          <input
            id={`flight-session-id-${droneId}`}
            type="text"
            value={sessionId}
            maxLength={36}
            placeholder="/mobile-flight 화면의 공통 UUID"
            onChange={(event) => setSessionId(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void loadReplay(sessionId);
              }
            }}
            className="min-w-0 flex-1 rounded-lg border border-cyan-300 bg-white px-3 py-2 font-mono text-sm"
          />
          <button
            type="button"
            onClick={() => void loadReplay(sessionId)}
            disabled={replayLoading}
            className="rounded-lg bg-cyan-700 px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {replayLoading ? "조회 중" : "세션 불러오기"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </div>
      )}

      {replay && (
        <div className="mt-4 space-y-4">
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
            <SummaryValue
              label="비행 시간"
              value={formatDuration(replay.durationSeconds)}
            />
            <SummaryValue
              label="경로 좌표"
              value={`${replay.telemetryCount}개`}
            />
            <SummaryValue
              label="AI 이벤트"
              value={`${replay.aiEventCount}건`}
            />
            <SummaryValue
              label="총 탐지"
              value={`${replay.detectionCount}개`}
            />
            <SummaryValue
              label="현재 재생 시각"
              value={
                currentTimeMs === null
                  ? "재생 대기"
                  : new Date(currentTimeMs).toLocaleTimeString("ko-KR")
              }
            />
          </div>

          <div className="text-xs text-cyan-900">
            {formatDateTime(replay.startedAt)} ~ {formatDateTime(replay.endedAt)}
          </div>

          <div className="rounded-xl border border-violet-200 bg-white p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="font-bold text-violet-950">
                현재 재생 위치의 AI 탐지
              </div>
              <span className="text-xs font-semibold text-violet-700">
                ±{EVENT_SYNC_WINDOW_MS / 1_000}초 동기화
              </span>
            </div>

            {activeEvent ? (
              <div className="mt-3 grid gap-3 sm:grid-cols-[180px_minmax(0,1fr)]">
                <div className="overflow-hidden rounded-lg bg-slate-950">
                  {activeEvent.snapshotAvailable ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={
                        activeEvent.snapshotUrl ??
                        `/api/ai/events/${activeEvent.id}/snapshot`
                      }
                      alt={`AI 탐지 이벤트 ${activeEvent.id}`}
                      className="aspect-video h-full w-full object-contain"
                    />
                  ) : (
                    <div className="flex aspect-video items-center justify-center text-xs text-slate-400">
                      저장된 스냅샷 없음
                    </div>
                  )}
                </div>

                <div className="text-sm">
                  <div className="font-bold text-slate-900">
                    #{activeEvent.frameIndex} · {eventClassNames(activeEvent)}
                  </div>
                  <div className="mt-1 text-slate-600">
                    {formatDateTime(activeEvent.capturedAt)} · 탐지{" "}
                    {activeEvent.detectionCount}개 · 추론{" "}
                    {Number(activeEvent.inferenceMs).toFixed(1)}ms
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {activeEvent.detections.map((detection) => (
                      <span
                        key={detection.id}
                        className="rounded-full bg-violet-100 px-2 py-1 text-xs font-semibold text-violet-800"
                      >
                        {detection.className}{" "}
                        {Math.round(Number(detection.confidence) * 100)}%
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-500">
                현재 재생 시각 ±5초 범위에 저장된 AI 탐지가 없습니다.
              </div>
            )}
          </div>

          {passedEvents.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="font-bold text-slate-900">통과한 탐지 이벤트</div>
              <div className="mt-2 grid gap-2 lg:grid-cols-2">
                {passedEvents.map((event) => (
                  <div
                    key={event.id}
                    className={`rounded-lg border p-3 text-sm ${
                      activeEvent?.id === event.id
                        ? "border-violet-400 bg-violet-50"
                        : "border-slate-200"
                    }`}
                  >
                    <div className="font-semibold text-slate-900">
                      #{event.frameIndex} · {eventClassNames(event)}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      {formatDateTime(event.capturedAt)} · {event.detectionCount}개
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="text-xs font-medium text-cyan-900">
            아래의 경로 재생 컨트롤에서 재생·일시정지·속도·슬라이더를 조작하세요.
          </div>
        </div>
      )}
    </section>
  );
}

function SummaryValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white p-3 text-center">
      <div className="text-xs font-semibold text-slate-500">{label}</div>
      <div className="mt-1 font-bold text-slate-900">{value}</div>
    </div>
  );
}

function SessionStatusBadge({
  status,
}: {
  status: FlightSessionSummary["status"];
}) {
  const presentation = {
    READY: {
      label: "준비",
      className: "bg-sky-100 text-sky-800",
    },
    ACTIVE: {
      label: "비행 중",
      className: "bg-emerald-100 text-emerald-800",
    },
    COMPLETED: {
      label: "완료",
      className: "bg-indigo-100 text-indigo-800",
    },
    ABORTED: {
      label: "중단",
      className: "bg-rose-100 text-rose-800",
    },
    LEGACY: {
      label: "기존 데이터",
      className: "bg-slate-200 text-slate-700",
    },
  }[status];

  return (
    <span
      className={`rounded-full px-2 py-1 text-[10px] font-bold ${presentation.className}`}
    >
      {presentation.label}
    </span>
  );
}

function SessionBadge({
  enabled,
  enabledLabel,
  disabledLabel,
}: {
  enabled: boolean;
  enabledLabel: string;
  disabledLabel: string;
}) {
  return (
    <span
      className={`rounded-full px-2 py-1 text-[10px] font-bold ${
        enabled
          ? "bg-emerald-100 text-emerald-800"
          : "bg-slate-100 text-slate-500"
      }`}
    >
      {enabled ? enabledLabel : disabledLabel}
    </span>
  );
}
