"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DroneTrackReplayControls,
  type DroneReplayState,
} from "./drone-track-replay-controls";
import dynamic from "next/dynamic";
import Link from "next/link";
import { DroneHistoryPanel } from "./drone-history-panel";
import { GeofenceManagementPanel } from "./geofence-management-panel";
import { AiInferenceEventPanel } from "./ai-inference-event-panel";
import { AiLiveStreamPanel } from "./ai-live-stream-panel";
import { FlightSessionReplayPanel } from "./flight-session-replay-panel";
import {
  useDroneFleetTelemetry,
  type DroneTrackPoint,
} from "@/hooks/use-drone-fleet-telemetry";
import type { Drone } from "@/types/drone";
import type { GeofenceDraft } from "@/types/geofence";
import type { IncidentReplayFocus } from "@/types/incident-replay";
import {
  parseMaintenanceFleetFlightClearance,
  type MaintenanceFleetFlightClearance,
  type MaintenanceFlightClearance,
} from "@/types/maintenance-flight-clearance";

const DroneControlMap = dynamic(() => import("./drone-control-map"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[680px] items-center justify-center rounded-2xl bg-slate-100 text-slate-500">
      관제 지도를 불러오는 중입니다.
    </div>
  ),
});

interface DroneFleetControlProps {
  initialDrones: Drone[];
  initialSelectedDroneId?: number | null;
  initialReplaySessionId?: string | null;
  initialIncidentFocus?: IncidentReplayFocus | null;
  initialFleetClearance?: MaintenanceFleetFlightClearance | null;
}

interface SessionReplayTrack {
  droneId: number;
  points: DroneTrackPoint[];
}

function connectionLabel(status: string): string {
  switch (status) {
    case "CONNECTED":
      return "실시간 연결";
    case "CONNECTING":
      return "연결 중";
    case "ERROR":
      return "연결 오류";
    default:
      return "연결 끊김";
  }
}

function formatEventTime(value: string): string {
  const normalized = value.replace(/(\.\d{3})\d+(?=Z|[+-]\d{2}:\d{2}|$)/, "$1");
  const date = new Date(normalized);

  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("ko-KR");
}

function findNearestPointIndex(
  points: DroneTrackPoint[],
  occurredAt: string,
): number {
  const targetTime = Date.parse(occurredAt);

  if (!Number.isFinite(targetTime) || points.length === 0) {
    return 0;
  }

  let nearestIndex = 0;
  let nearestDistance = Number.POSITIVE_INFINITY;

  points.forEach((point, index) => {
    const distance = Math.abs(point.receivedAt - targetTime);

    if (distance < nearestDistance) {
      nearestIndex = index;
      nearestDistance = distance;
    }
  });

  return nearestIndex;
}

function maintenanceWorkOrderHref(
  droneId: number,
  clearance: MaintenanceFlightClearance,
): string {
  const query = new URLSearchParams({ droneId: String(droneId) });
  if (clearance.workOrderId !== null) {
    query.set("workOrderId", String(clearance.workOrderId));
  }
  return `/maintenance?${query}`;
}

export function DroneFleetControl({
  initialDrones,
  initialSelectedDroneId = null,
  initialReplaySessionId = null,
  initialIncidentFocus = null,
  initialFleetClearance = null,
}: DroneFleetControlProps) {
  const {
    drones,
    connectionStatus,
    lastMessageAt,
    tracksByDroneId,
    geofences,
    geofenceEvents,
    geofenceLoadError,
    refreshGeofences,
    aiEvents,
    aiEventLoadError,
    refreshAiEvents,
    clearTrack,
    replaceTrack,
  } = useDroneFleetTelemetry(initialDrones);

  const [selectedDroneId, setSelectedDroneId] = useState<number | null>(() =>
    initialSelectedDroneId !== null &&
    initialDrones.some((drone) => drone.id === initialSelectedDroneId)
      ? initialSelectedDroneId
      : initialDrones[0]?.id ?? null,
  );

  const [replayState, setReplayState] = useState<DroneReplayState | null>(null);

  const [sessionReplayTrack, setSessionReplayTrack] =
    useState<SessionReplayTrack | null>(null);

  const [incidentFocus, setIncidentFocus] =
    useState<IncidentReplayFocus | null>(initialIncidentFocus);

  const [fleetClearance, setFleetClearance] =
    useState<MaintenanceFleetFlightClearance | null>(
      initialFleetClearance,
    );
  const [clearanceLoadError, setClearanceLoadError] =
    useState<string | null>(null);
  const [clearanceRefreshing, setClearanceRefreshing] = useState(false);

  const [geofenceDraft, setGeofenceDraft] = useState<GeofenceDraft | null>(
    null,
  );

  const [fleetPanelCollapsed, setFleetPanelCollapsed] = useState(false);

  const replayIsPlaying = replayState?.isPlaying ?? false;

  const replayIntervalMs = replayState?.intervalMs ?? 1_000;

  const refreshFleetClearance = useCallback(
    async (signal?: AbortSignal) => {
      setClearanceRefreshing(true);
      try {
        const response = await fetch(
          "/api/maintenance/flight-clearance",
          {
            method: "GET",
            headers: { Accept: "application/json" },
            cache: "no-store",
            signal,
          },
        );
        if (!response.ok) {
          throw new Error(
            `함대 비행 허가 상태 조회 실패: ${response.status}`,
          );
        }

        const parsed = parseMaintenanceFleetFlightClearance(
          await response.json() as unknown,
        );
        if (!parsed) {
          throw new Error(
            "함대 비행 허가 상태 응답 형식이 올바르지 않습니다.",
          );
        }

        if (!signal?.aborted) {
          setFleetClearance(parsed);
          setClearanceLoadError(null);
        }
      } catch (error) {
        if (!signal?.aborted) {
          setClearanceLoadError(
            error instanceof Error
              ? error.message
              : "함대 비행 허가 상태를 불러오지 못했습니다.",
          );
        }
      } finally {
        if (!signal?.aborted) {
          setClearanceRefreshing(false);
        }
      }
    },
    [],
  );

  useEffect(() => {
    const abortController = new AbortController();
    const initialTimerId =
      initialFleetClearance === null
        ? window.setTimeout(() => {
            void refreshFleetClearance(abortController.signal);
          }, 0)
        : undefined;
    const intervalId = window.setInterval(() => {
      void refreshFleetClearance(abortController.signal);
    }, 30_000);

    return () => {
      if (initialTimerId !== undefined) {
        window.clearTimeout(initialTimerId);
      }
      window.clearInterval(intervalId);
      abortController.abort();
    };
  }, [initialFleetClearance, refreshFleetClearance]);

  useEffect(() => {
    if (!replayIsPlaying) {
      return;
    }

    const timerId = window.setInterval(() => {
      setReplayState((current) => {
        if (!current || !current.isPlaying) {
          return current;
        }

        const lastIndex = Math.max(current.pointCount - 1, 0);

        if (current.cursor >= lastIndex) {
          return {
            ...current,
            isPlaying: false,
          };
        }

        const nextCursor = current.cursor + 1;

        return {
          ...current,
          cursor: nextCursor,
          isPlaying: nextCursor < lastIndex,
        };
      });
    }, replayIntervalMs);

    return () => {
      window.clearInterval(timerId);
    };
  }, [replayIntervalMs, replayIsPlaying]);

  const selectedDrone = useMemo(
    () =>
      drones.find((drone) => drone.id === selectedDroneId) ?? drones[0] ?? null,
    [drones, selectedDroneId],
  );

  const effectiveSelectedId = selectedDrone?.id ?? null;

  function handleSelectDrone(droneId: number) {
    if (droneId !== effectiveSelectedId) {
      setReplayState(null);
      setSessionReplayTrack(null);
      setIncidentFocus(null);
    }

    setSelectedDroneId(droneId);
  }

  function handlePickGeofenceCenter(latitude: number, longitude: number) {
    setGeofenceDraft((current) =>
      current
        ? {
            ...current,
            centerLatitude: Number(latitude.toFixed(7)),
            centerLongitude: Number(longitude.toFixed(7)),
          }
        : current,
    );
  }

  const selectedSourceTrack = useMemo(() => {
    if (effectiveSelectedId === null) {
      return [];
    }

    if (sessionReplayTrack?.droneId === effectiveSelectedId) {
      return sessionReplayTrack.points;
    }

    return tracksByDroneId[effectiveSelectedId] ?? [];
  }, [effectiveSelectedId, sessionReplayTrack, tracksByDroneId]);

  const displayedTracksByDroneId = useMemo(() => {
    if (!replayState || replayState.droneId !== effectiveSelectedId) {
      return tracksByDroneId;
    }

    const pointCount = Math.min(
      replayState.pointCount,
      selectedSourceTrack.length,
    );

    const cursor = Math.min(replayState.cursor, Math.max(pointCount - 1, 0));

    return {
      ...tracksByDroneId,
      [replayState.droneId]: selectedSourceTrack.slice(0, cursor + 1),
    };
  }, [effectiveSelectedId, replayState, selectedSourceTrack, tracksByDroneId]);

  const replayPoint = useMemo(() => {
    if (!replayState || replayState.droneId !== effectiveSelectedId) {
      return null;
    }

    const lastSnapshotIndex =
      Math.min(replayState.pointCount, selectedSourceTrack.length) - 1;

    if (lastSnapshotIndex < 0) {
      return null;
    }

    const safeCursor = Math.min(
      Math.max(replayState.cursor, 0),
      lastSnapshotIndex,
    );

    const point = selectedSourceTrack[safeCursor];

    if (!point) {
      return null;
    }

    return {
      droneId: replayState.droneId,
      point,
    };
  }, [effectiveSelectedId, replayState, selectedSourceTrack]);

  const flyingCount = drones.filter(
    (drone) => !drone.isStale && drone.status === "FLYING",
  ).length;

  const staleCount = drones.filter((drone) => drone.isStale).length;

  const clearanceByDroneId = useMemo(
    () =>
      new Map<number, MaintenanceFlightClearance>(
        (fleetClearance?.clearances ?? []).map((clearance) => [
          clearance.droneId,
          clearance,
        ]),
      ),
    [fleetClearance],
  );

  const activeGeofenceEvents = useMemo(
    () => geofenceEvents.filter((event) => event.state === "ACTIVE"),
    [geofenceEvents],
  );

  const activeGeofenceIds = useMemo(
    () =>
      Array.from(
        new Set(activeGeofenceEvents.map((event) => event.geofenceId)),
      ),
    [activeGeofenceEvents],
  );

  const violatingDroneIds = useMemo(
    () => new Set(activeGeofenceEvents.map((event) => event.droneId)),
    [activeGeofenceEvents],
  );

  return (
    <section className="vf-fleet-control space-y-6">
      <div className="vf-fleet-map-title mb-2 flex flex-wrap items-end justify-between gap-3 px-1">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.2em] text-sky-700">
            Live Operations Map
          </p>
          <h1 className="mt-1 text-2xl font-black tracking-tight text-slate-950">
            함대 실시간 위치
          </h1>
        </div>
        <p className="text-xs font-medium text-slate-500">
          기체 선택 · 이동 경로 · 지오펜스 · Incident 포커스
        </p>
      </div>

      <section className="vf-fleet-map-shell relative overflow-hidden rounded-3xl border border-slate-200 bg-slate-100 shadow-sm">
        <div className="pointer-events-none absolute right-4 top-4 z-[500] hidden items-center gap-2 rounded-full border border-slate-200 bg-white/95 px-2.5 py-1.5 text-[11px] font-black text-slate-700 shadow-lg backdrop-blur xl:flex">
          <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true" />
          Live fleet map
        </div>

        {fleetPanelCollapsed && (
          <button
            type="button"
            onClick={() => setFleetPanelCollapsed(false)}
            aria-expanded="false"
            className="absolute left-16 top-4 z-[520] hidden items-center gap-2 rounded-xl border border-slate-200 bg-white/95 px-3 py-2 text-xs font-black text-slate-800 shadow-lg backdrop-blur transition hover:bg-white xl:flex"
          >
            <span aria-hidden="true">☰</span>
            함대 {drones.length}대
          </button>
        )}
        {!fleetPanelCollapsed && (
          <aside className="vf-fleet-roster max-h-[620px] space-y-3 overflow-y-auto border-b border-slate-200 bg-white p-3 shadow-sm xl:absolute xl:left-16 xl:top-4 xl:z-[500] xl:w-[300px] xl:rounded-2xl xl:border xl:bg-white/95 xl:backdrop-blur">
            <div className="flex items-start justify-between gap-3 px-1 pb-1">
              <div>
                <h2 className="text-sm font-black text-slate-950">함대 기체</h2>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  기체를 선택하면 지도와 상세 패널이 동기화됩니다.
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-black text-slate-700">
                  {drones.length}대
                </span>
                <button
                  type="button"
                  onClick={() => setFleetPanelCollapsed(true)}
                  aria-label="함대 패널 접기"
                  aria-expanded="true"
                  className="hidden rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-black text-slate-600 transition hover:bg-slate-50 xl:inline-flex"
                >
                  접기
                </button>
              </div>
            </div>

          {drones.map((drone) => {
            const selected = drone.id === effectiveSelectedId;
            const violating = violatingDroneIds.has(drone.id);
            const clearance = clearanceByDroneId.get(drone.id);
            const flightBlocked =
              clearance !== undefined && !clearance.flightAllowed;
            const flightAttention =
              clearance?.attentionRequired === true && !flightBlocked;

            return (
              <div key={drone.id} className="relative">
                <button
                  type="button"
                  onClick={() => handleSelectDrone(drone.id)}
                  className={`vf-fleet-card w-full rounded-xl border p-4 text-left transition ${
                    clearance?.workOrderId !== null &&
                    clearance?.workOrderId !== undefined
                      ? "pb-14"
                      : ""
                  } ${
                  selected
                    ? "border-blue-500 bg-blue-50"
                    : flightBlocked
                      ? "border-red-500 bg-red-50 hover:border-red-600"
                    : violating
                      ? "border-red-400 bg-red-50 hover:border-red-500"
                      : flightAttention
                        ? "border-amber-400 bg-amber-50 hover:border-amber-500"
                      : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-slate-900">
                      {drone.name}
                    </div>

                    <div className="text-xs text-slate-500">
                      {drone.droneCode}
                    </div>
                  </div>

                  <div className="flex flex-col items-end gap-1">
                    <span
                      className={`rounded-full px-2 py-1 text-xs font-semibold ${
                        drone.isStale
                          ? "bg-slate-100 text-slate-600"
                          : "bg-emerald-100 text-emerald-700"
                      }`}
                    >
                      {drone.isStale ? "STALE" : drone.status}
                    </span>

                    {violating && (
                      <span className="rounded-full bg-red-600 px-2 py-1 text-xs font-bold text-white">
                        GEOFENCE
                      </span>
                    )}

                    {clearance && (
                      <span
                        className={`rounded-full px-2 py-1 text-xs font-bold ${
                          flightBlocked
                            ? "bg-red-600 text-white"
                            : flightAttention
                              ? "bg-amber-100 text-amber-800"
                              : "bg-emerald-100 text-emerald-700"
                        }`}
                      >
                        {flightBlocked
                          ? "비행 차단"
                          : flightAttention
                            ? "점검 주의"
                            : clearance.clearanceStatus === "CLEARED"
                              ? "재운항 승인"
                              : "비행 가능"}
                      </span>
                    )}
                  </div>
                  </div>

                  <div className="mt-3 grid grid-cols-2 gap-2 text-sm text-slate-600">
                    <span>배터리 {drone.batteryLevel ?? 0}%</span>

                    <span>고도 {drone.altitude ?? 0}m</span>
                  </div>
                </button>
                {clearance?.workOrderId !== null &&
                  clearance?.workOrderId !== undefined && (
                    <Link
                      href={maintenanceWorkOrderHref(drone.id, clearance)}
                      className="absolute bottom-3 left-4 right-4 rounded-lg border border-cyan-300 bg-white px-3 py-2 text-center text-xs font-bold text-cyan-800 shadow-sm hover:bg-cyan-50"
                    >
                      점검 작업 #{clearance.workOrderId} 처리
                    </Link>
                  )}
              </div>
            );
          })}

            {drones.length === 0 && (
              <div className="p-8 text-center text-sm text-slate-500">
                등록된 드론이 없습니다.
              </div>
            )}
          </aside>
        )}

        <div className="h-[72vh] min-h-[520px] overflow-hidden bg-white lg:h-[calc(100vh-190px)] lg:min-h-[620px] lg:max-h-[820px]">
          <DroneControlMap
            drones={drones}
            tracksByDroneId={displayedTracksByDroneId}
            geofences={geofences}
            activeGeofenceIds={activeGeofenceIds}
            geofenceDraft={geofenceDraft}
            onPickGeofenceCenter={handlePickGeofenceCenter}
            replayPoint={replayPoint}
            incidentFocus={incidentFocus}
            flightClearanceByDroneId={clearanceByDroneId}
            selectedDroneId={effectiveSelectedId}
            onSelectDrone={handleSelectDrone}
          />
        </div>
      </section>

      <header className="vf-fleet-command-header overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-5 p-5 sm:p-6 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-3xl">
            <p className="text-xs font-black uppercase tracking-[0.2em] text-sky-700">
              Fleet Mission Control
            </p>
            <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-950">
              실시간 드론 관제
            </h1>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              기체 연결, 비행 허가, 지오펜스와 AI 이벤트를 한 화면에서
              판단합니다.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2 xl:justify-end">
            <span
              aria-live="polite"
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-black ${
                connectionStatus === "CONNECTED"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                  : connectionStatus === "CONNECTING"
                    ? "border-amber-200 bg-amber-50 text-amber-800"
                    : "border-rose-200 bg-rose-50 text-rose-800"
              }`}
            >
              <span
                aria-hidden="true"
                className={`h-2.5 w-2.5 rounded-full ${
                  connectionStatus === "CONNECTED"
                    ? "bg-emerald-500"
                    : connectionStatus === "CONNECTING"
                      ? "bg-amber-500"
                      : "bg-rose-500"
                }`}
              />
              {connectionLabel(connectionStatus)}
            </span>

            <Link
              href="/mobile-control"
              className="rounded-xl bg-slate-950 px-4 py-2 text-xs font-black text-white transition hover:bg-slate-800"
            >
              스마트폰 가상 드론
            </Link>
          </div>
        </div>

        <div className="grid border-t border-slate-200 sm:grid-cols-2 lg:grid-cols-5">
          <FleetOverviewMetric
            label="전체 기체"
            value={`${drones.length}대`}
            hint="등록된 관제 대상"
          />
          <FleetOverviewMetric
            label="비행 중"
            value={`${flyingCount}대`}
            hint="실시간 ACTIVE"
            tone="emerald"
          />
          <FleetOverviewMetric
            label="통신 지연"
            value={`${staleCount}대`}
            hint="stale telemetry"
            tone={staleCount > 0 ? "amber" : "slate"}
          />
          <FleetOverviewMetric
            label="활성 경보"
            value={`${activeGeofenceEvents.length}건`}
            hint={`지오펜스 ${geofences.length}개`}
            tone={activeGeofenceEvents.length > 0 ? "rose" : "slate"}
          />
          <FleetOverviewMetric
            label="비행 차단"
            value={`${fleetClearance?.blockedDrones ?? 0}대`}
            hint={`점검 주의 ${fleetClearance?.attentionDrones ?? 0} · AI ${aiEvents.length}`}
            tone={(fleetClearance?.blockedDrones ?? 0) > 0 ? "rose" : "slate"}
          />
        </div>

        <div className="vf-fleet-connection-strip flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 bg-slate-50/80 px-5 py-3 text-xs font-medium text-slate-600 sm:px-6">
          <span>
            WebSocket · <strong className="text-slate-900">{connectionStatus}</strong>
          </span>
          <span>
            마지막 수신{" "}
            <strong className="text-slate-900">
              {lastMessageAt ? lastMessageAt.toLocaleTimeString("ko-KR") : "-"}
            </strong>
          </span>
        </div>
      </header>

      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-bold text-slate-950">
                함대 비행 허가 현황
              </h2>
              <span
                className={`rounded-full px-2.5 py-1 text-xs font-bold ${
                  fleetClearance?.enforced
                    ? "bg-red-100 text-red-700"
                    : "bg-sky-100 text-sky-700"
                }`}
              >
                {fleetClearance?.mode ?? "조회 중"}
              </span>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              정비 작업지시와 재운항 승인 결과를 기준으로 30초마다 갱신합니다.
              {fleetClearance
                ? ` 마지막 평가 ${new Date(
                    fleetClearance.evaluatedAt,
                  ).toLocaleTimeString("ko-KR")}`
                : ""}
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <Link
              href="/maintenance"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50"
            >
              점검 작업 열기
            </Link>
            <button
              type="button"
              onClick={() => void refreshFleetClearance()}
              disabled={clearanceRefreshing}
              className="rounded-lg bg-slate-950 px-3 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {clearanceRefreshing ? "갱신 중" : "허가 상태 새로고침"}
            </button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <ClearanceMetric
            label="전체 기체"
            value={fleetClearance?.totalDrones ?? drones.length}
            className="border-slate-200 bg-slate-50 text-slate-800"
          />
          <ClearanceMetric
            label="비행 가능"
            value={fleetClearance?.allowedDrones ?? 0}
            className="border-emerald-200 bg-emerald-50 text-emerald-800"
          />
          <ClearanceMetric
            label="점검 주의"
            value={fleetClearance?.attentionDrones ?? 0}
            className="border-amber-200 bg-amber-50 text-amber-800"
          />
          <ClearanceMetric
            label="비행 차단"
            value={fleetClearance?.blockedDrones ?? 0}
            className="border-red-200 bg-red-50 text-red-800"
          />
        </div>

        {clearanceLoadError && (
          <div className="mt-3 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-800">
            {clearanceLoadError}
          </div>
        )}
      </div>

      {incidentFocus && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-violet-300 bg-violet-50 p-4">
          <div>
            <div className="font-bold text-violet-950">
              Incident #{incidentFocus.incidentId} 발생 지점 포커스
            </div>
            <div className="mt-1 text-sm text-violet-800">
              {{
                AI_ALERT: "AI 경보",
                GEOFENCE: "지오펜스",
                FLIGHT_QUALITY: "기체 신뢰도",
                FLIGHT_GATE: "비행 시작 차단",
              }[incidentFocus.sourceType]}{" "}
              · {formatEventTime(incidentFocus.occurredAt)}
            </div>
            <div className="mt-1 text-xs text-violet-700">
              연결된 비행 세션이 있으면 경로와 영상 증거가 발생 시각으로 자동 이동합니다.
            </div>
          </div>
          <button
            type="button"
            onClick={() => setIncidentFocus(null)}
            className="rounded-lg border border-violet-300 bg-white px-3 py-2 text-sm font-bold text-violet-800 hover:bg-violet-100"
          >
            포커스 해제
          </button>
        </div>
      )}

      <GeofenceManagementPanel
        geofences={geofences}
        draft={geofenceDraft}
        onDraftChange={setGeofenceDraft}
        onRefresh={refreshGeofences}
      />

      {geofenceLoadError && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800">
          지오펜스 데이터를 불러오지 못했습니다: {geofenceLoadError}
        </div>
      )}

      {activeGeofenceEvents.length > 0 && (
        <div className="rounded-2xl border border-red-300 bg-red-50 p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="font-bold text-red-900">지오펜스 침범 경보</div>
              <div className="text-sm text-red-700">
                현재 해결되지 않은 경보가 {activeGeofenceEvents.length}건
                있습니다.
              </div>
            </div>

            <span className="rounded-full bg-red-600 px-3 py-1 text-sm font-bold text-white">
              ACTIVE
            </span>
          </div>

          <div className="grid gap-2 lg:grid-cols-2">
            {activeGeofenceEvents.map((event) => (
              <button
                key={event.id}
                type="button"
                onClick={() => handleSelectDrone(event.droneId)}
                className="rounded-xl border border-red-200 bg-white p-3 text-left transition hover:border-red-400"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="font-semibold text-red-900">
                    {event.droneCode} · {event.geofenceName}
                  </div>
                  <span className="text-xs font-semibold text-red-600">
                    {event.ruleType === "KEEP_OUT"
                      ? "진입 금지 침범"
                      : "허용 구역 이탈"}
                  </span>
                </div>

                <div className="mt-1 text-xs text-slate-600">
                  중심 거리 {Math.round(Number(event.distanceMeters))}m ·{" "}
                  {formatEventTime(event.detectedAt)}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}



      <AiLiveStreamPanel events={aiEvents} onSelectDrone={handleSelectDrone} />

      <AiInferenceEventPanel
        events={aiEvents}
        drones={drones}
        selectedDroneId={effectiveSelectedId}
        loadError={aiEventLoadError}
        onRefresh={refreshAiEvents}
        onSelectDrone={handleSelectDrone}
      />

      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <div className="font-semibold text-slate-900">
              최근 지오펜스 이벤트
            </div>
            <div className="text-sm text-slate-500">
              침범 발생과 정상 복귀 결과를 최근 순으로 표시합니다.
            </div>
          </div>

          <span className="text-sm font-semibold text-slate-600">
            총 {geofenceEvents.length}건
          </span>
        </div>

        {geofenceEvents.length === 0 ? (
          <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">
            아직 지오펜스 이벤트가 없습니다.
          </div>
        ) : (
          <div className="grid gap-2 lg:grid-cols-2">
            {geofenceEvents.slice(0, 8).map((event) => (
              <button
                key={event.id}
                type="button"
                onClick={() => handleSelectDrone(event.droneId)}
                className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 p-3 text-left hover:border-slate-400"
              >
                <div>
                  <div className="text-sm font-semibold text-slate-900">
                    {event.droneCode} · {event.geofenceName}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {formatEventTime(event.detectedAt)}
                  </div>
                </div>

                <span
                  className={`rounded-full px-2 py-1 text-xs font-bold ${
                    event.state === "ACTIVE"
                      ? "bg-red-100 text-red-700"
                      : "bg-emerald-100 text-emerald-700"
                  }`}
                >
                  {event.state === "ACTIVE" ? "침범 중" : "해결됨"}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {selectedDrone && (
        <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="font-semibold text-slate-900">
                선택된 드론: {selectedDrone.name}
              </div>

              <div className="mt-1 text-sm text-slate-500">
                {selectedDrone.modelName} · 배터리{" "}
                {selectedDrone.batteryLevel ?? 0}% · 고도{" "}
                {selectedDrone.altitude ?? 0}m · 경로{" "}
                {selectedSourceTrack.length}개
              </div>
              {clearanceByDroneId.get(selectedDrone.id) && (
                <div className="mt-2 text-sm font-medium text-slate-700">
                  비행 허가:{" "}
                  {clearanceByDroneId.get(selectedDrone.id)?.reason}
                </div>
              )}
            </div>

            <div className="flex flex-wrap gap-2">
              {clearanceByDroneId.get(selectedDrone.id)?.workOrderId !==
                null &&
                clearanceByDroneId.get(selectedDrone.id)?.workOrderId !==
                  undefined && (
                  <Link
                    href={maintenanceWorkOrderHref(
                      selectedDrone.id,
                      clearanceByDroneId.get(
                        selectedDrone.id,
                      ) as MaintenanceFlightClearance,
                    )}
                    className="rounded-lg border border-cyan-300 bg-cyan-50 px-4 py-2 text-sm font-semibold text-cyan-800"
                  >
                    연결된 점검 작업 열기
                  </Link>
                )}
              <button
                type="button"
                onClick={() => {
                  setReplayState(null);
                  setSessionReplayTrack(null);
                  clearTrack(selectedDrone.id);
                }}
                disabled={selectedSourceTrack.length === 0}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                경로 지우기
              </button>

              <Link
                href={`/drones/${selectedDrone.id}`}
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
              >
                상세 관제 열기
              </Link>
            </div>
          </div>

          <FlightSessionReplayPanel
            key={
              `session-replay-${selectedDrone.id}-` +
              `${initialReplaySessionId ?? "none"}-` +
              `${initialIncidentFocus?.incidentId ?? "none"}`
            }
            droneId={selectedDrone.id}
            initialSessionId={
              selectedDrone.id === initialSelectedDroneId
                ? initialReplaySessionId
                : null
            }
            currentTimeMs={
              replayState?.droneId === selectedDrone.id
                ? replayPoint?.point.receivedAt ?? null
                : null
            }
            onReplayLoaded={(_, points) => {
              const focusCursor = incidentFocus
                ? findNearestPointIndex(points, incidentFocus.occurredAt)
                : 0;

              setSessionReplayTrack({
                droneId: selectedDrone.id,
                points,
              });
              setReplayState({
                droneId: selectedDrone.id,
                pointCount: points.length,
                cursor: focusCursor,
                isPlaying: false,
                intervalMs: 1_000,
              });
            }}
          />

          <DroneHistoryPanel
            key={`history-${selectedDrone.id}`}
            droneId={selectedDrone.id}
            currentPointCount={tracksByDroneId[selectedDrone.id]?.length ?? 0}
            onHistoryLoaded={(points) => {
              setReplayState(null);
              setSessionReplayTrack(null);

              replaceTrack(selectedDrone.id, points);
            }}
          />

          <DroneTrackReplayControls
            key={`replay-${selectedDrone.id}`}
            droneId={selectedDrone.id}
            points={selectedSourceTrack}
            replayState={
              replayState?.droneId === selectedDrone.id ? replayState : null
            }
            onChange={setReplayState}
            onExit={() => {
              setReplayState(null);
              setSessionReplayTrack(null);
            }}
          />
        </div>
      )}
    </section>
  );
}

function FleetOverviewMetric({
  label,
  value,
  hint,
  tone = "slate",
}: {
  label: string;
  value: string;
  hint: string;
  tone?: "slate" | "emerald" | "amber" | "rose";
}) {
  const toneClassName = {
    slate: "bg-white",
    emerald: "bg-emerald-50/70",
    amber: "bg-amber-50/70",
    rose: "bg-rose-50/70",
  }[tone];

  const valueClassName = {
    slate: "text-slate-950",
    emerald: "text-emerald-800",
    amber: "text-amber-800",
    rose: "text-rose-800",
  }[tone];

  return (
    <div className={`vf-fleet-metric min-w-0 border-slate-200 px-5 py-4 lg:border-r lg:last:border-r-0 ${toneClassName}`}>
      <div className="text-[11px] font-black uppercase tracking-[0.16em] text-slate-500">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-black tracking-tight ${valueClassName}`}>
        {value}
      </div>
      <div className="mt-1 truncate text-xs font-medium text-slate-500">
        {hint}
      </div>
    </div>
  );
}

function ClearanceMetric({
  label,
  value,
  className,
}: {
  label: string;
  value: number;
  className: string;
}) {
  return (
    <div className={`rounded-xl border px-4 py-3 ${className}`}>
      <div className="text-xs font-semibold">{label}</div>
      <div className="mt-1 text-xl font-black">{value}대</div>
    </div>
  );
}
